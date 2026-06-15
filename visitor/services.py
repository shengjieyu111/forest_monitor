import csv
import os
import shlex
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Avg
from django.utils import timezone

from .models import (
    VisitorDailyStat,
    VisitorGateStat,
    VisitorHourlyStat,
    VisitorRecord,
)


CSV_FIELDS = [
    "record_id",
    "visit_time",
    "gate",
    "visitor_count",
    "weather",
    "ticket_type",
]

SSH_HOST = os.getenv("HADOOP_SSH_HOST", "192.168.56.100")
SSH_PORT = int(os.getenv("HADOOP_SSH_PORT", "22"))
SSH_USERNAME = os.getenv("HADOOP_SSH_USER", "root")
SSH_PASSWORD = os.getenv("HADOOP_SSH_PASSWORD")
SSH_KEY_FILENAME = os.getenv("HADOOP_SSH_KEY_FILENAME")
REMOTE_HADOOP_DIR = "/root/forest_monitor/hadoop"
REMOTE_DATASET_DIR = "/root/forest_monitor/datasets"
# HDFS 数据按 date=YYYY-MM-DD 分区存储，MapReduce 从根目录递归读取。
HDFS_INPUT_PATH = "/forest/visitor/input"
LOCAL_DATASET_DIR = Path(settings.BASE_DIR) / "datasets"
LOCAL_HADOOP_DIR = Path(settings.BASE_DIR) / "hadoop"


@dataclass
class ImportResult:
    file_path: str
    total_rows: int
    imported_rows: int
    skipped_rows: int


@dataclass
class MapReduceImportResult:
    daily_rows: int
    hourly_rows: int
    gate_rows: int


@dataclass
class SSHCommandResult:
    command: str
    exit_status: int
    stdout: str
    stderr: str

    @property
    def success(self):
        return self.exit_status == 0


def parse_visit_time(value):
    visit_time = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    if timezone.is_naive(visit_time):
        return timezone.make_aware(visit_time, timezone.get_current_timezone())
    return visit_time


def build_visitor_record(row):
    return VisitorRecord(
        visit_time=parse_visit_time(row["visit_time"]),
        gate=row["gate"],
        visitor_count=int(row["visitor_count"]),
        weather=row["weather"],
        ticket_type=row["ticket_type"],
    )


def validate_csv_header(fieldnames):
    if fieldnames is None:
        raise ValueError("CSV 文件为空，未读取到表头。")

    missing_fields = [field for field in CSV_FIELDS if field not in fieldnames]
    if missing_fields:
        raise ValueError(f"CSV 表头缺少字段：{', '.join(missing_fields)}")


def flush_batch(batch):
    if not batch:
        return 0

    VisitorRecord.objects.bulk_create(batch, batch_size=len(batch))
    return len(batch)


def import_visitor_records_from_csv(
    csv_path="datasets/visitor_records.csv",
    batch_size=5000,
    clear_existing=False,
):
    """
    将游客模拟 CSV 数据批量导入 MySQL 的 visitor_record 表。

    CSV 字段：record_id,visit_time,gate,visitor_count,weather,ticket_type
    record_id 只作为 CSV 行编号保留，导入数据库时使用 Django 自动生成的 id。
    """
    file_path = Path(csv_path)
    if not file_path.exists():
        raise FileNotFoundError(f"CSV 文件不存在：{file_path}")

    total_rows = 0
    imported_rows = 0
    skipped_rows = 0
    batch = []

    if clear_existing:
        with transaction.atomic():
            VisitorRecord.objects.all().delete()

    with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        validate_csv_header(reader.fieldnames)

        for row in reader:
            total_rows += 1
            try:
                batch.append(build_visitor_record(row))
            except (KeyError, ValueError) as exc:
                skipped_rows += 1
                print(f"第 {total_rows} 行导入失败，已跳过：{exc}")
                continue

            if len(batch) >= batch_size:
                imported_rows += flush_batch(batch)
                batch = []

        imported_rows += flush_batch(batch)

    return ImportResult(
        file_path=str(file_path),
        total_rows=total_rows,
        imported_rows=imported_rows,
        skipped_rows=skipped_rows,
    )


def import_visitor_records_for_date(csv_path, date_str):
    """用指定日期 CSV 覆盖 MySQL 中同一天的游客原始记录。"""
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    file_path = Path(csv_path)
    if not file_path.exists():
        raise FileNotFoundError(f"CSV 文件不存在：{file_path}")

    records = []
    total_rows = 0
    with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        validate_csv_header(reader.fieldnames)
        for row in reader:
            total_rows += 1
            record = build_visitor_record(row)
            if record.visit_time.date() != target_date:
                raise ValueError(
                    f"CSV 第 {total_rows + 1} 行日期不是 {date_str}："
                    f"{record.visit_time:%Y-%m-%d}"
                )
            records.append(record)

    if not records:
        raise ValueError("CSV 中没有可导入的游客记录。")

    with transaction.atomic():
        VisitorRecord.objects.filter(visit_time__date=target_date).delete()
        VisitorRecord.objects.bulk_create(records, batch_size=5000)

    return ImportResult(
        file_path=str(file_path),
        total_rows=total_rows,
        imported_rows=len(records),
        skipped_rows=0,
    )


def import_local_date_partitions():
    """把 HDFS 页面保存的本地日期增量 CSV 同步到 MySQL。"""
    upload_dir = LOCAL_DATASET_DIR / "upload_date"
    imported_rows = 0
    imported_files = 0
    if not upload_dir.exists():
        return {"imported_files": 0, "imported_rows": 0}

    for file_path in sorted(upload_dir.glob("visitor_records_????-??-??.csv")):
        date_str = file_path.stem.removeprefix("visitor_records_")
        result = import_visitor_records_for_date(file_path, date_str)
        imported_files += 1
        imported_rows += result.imported_rows

    return {"imported_files": imported_files, "imported_rows": imported_rows}


def read_mapreduce_rows(file_path):
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"MapReduce 结果文件不存在：{path}")

    rows = []
    with path.open("r", encoding="utf-8-sig") as result_file:
        for line_number, line in enumerate(result_file, start=1):
            line = line.strip()
            if not line:
                continue

            parts = line.split()
            if len(parts) != 2:
                raise ValueError(f"{path.name} 第 {line_number} 行格式错误：{line}")
            rows.append((parts[0], parts[1]))
    return rows


def import_mapreduce_results(
    daily_path="datasets/visitor_daily_result.txt",
    hourly_path="datasets/visitor_hourly_result.txt",
    gate_path="datasets/visitor_gate_result.txt",
    clear_existing=True,
):
    """将三个 MapReduce 结果文件导入对应的 MySQL 统计表。"""
    daily_stats = [
        VisitorDailyStat(
            stat_date=datetime.strptime(stat_date, "%Y-%m-%d").date(),
            total_count=int(total_count),
        )
        for stat_date, total_count in read_mapreduce_rows(daily_path)
    ]
    hourly_stats = [
        VisitorHourlyStat(hour=int(hour), total_count=int(total_count))
        for hour, total_count in read_mapreduce_rows(hourly_path)
    ]
    gate_stats = [
        VisitorGateStat(gate=gate, total_count=int(total_count))
        for gate, total_count in read_mapreduce_rows(gate_path)
    ]

    with transaction.atomic():
        if clear_existing:
            VisitorDailyStat.objects.all().delete()
            VisitorHourlyStat.objects.all().delete()
            VisitorGateStat.objects.all().delete()

        VisitorDailyStat.objects.bulk_create(daily_stats, batch_size=1000)
        VisitorHourlyStat.objects.bulk_create(hourly_stats, batch_size=1000)
        VisitorGateStat.objects.bulk_create(gate_stats, batch_size=1000)

    return MapReduceImportResult(
        daily_rows=len(daily_stats),
        hourly_rows=len(hourly_stats),
        gate_rows=len(gate_stats),
    )


def import_daily_result(file_path=None, clear_existing=True):
    path = file_path or LOCAL_DATASET_DIR / "visitor_daily_result.txt"
    stats = [
        VisitorDailyStat(
            stat_date=datetime.strptime(stat_date, "%Y-%m-%d").date(),
            total_count=int(total_count),
        )
        for stat_date, total_count in read_mapreduce_rows(path)
    ]
    with transaction.atomic():
        if clear_existing:
            VisitorDailyStat.objects.all().delete()
        VisitorDailyStat.objects.bulk_create(stats, batch_size=1000)
    return len(stats)


def import_hourly_result(file_path=None, clear_existing=True):
    path = file_path or LOCAL_DATASET_DIR / "visitor_hourly_result.txt"
    stats = [
        VisitorHourlyStat(hour=int(hour), total_count=int(total_count))
        for hour, total_count in read_mapreduce_rows(path)
    ]
    with transaction.atomic():
        if clear_existing:
            VisitorHourlyStat.objects.all().delete()
        VisitorHourlyStat.objects.bulk_create(stats, batch_size=1000)
    return len(stats)


def import_gate_result(file_path=None, clear_existing=True):
    path = file_path or LOCAL_DATASET_DIR / "visitor_gate_result.txt"
    stats = [
        VisitorGateStat(gate=gate, total_count=int(total_count))
        for gate, total_count in read_mapreduce_rows(path)
    ]
    with transaction.atomic():
        if clear_existing:
            VisitorGateStat.objects.all().delete()
        VisitorGateStat.objects.bulk_create(stats, batch_size=1000)
    return len(stats)


def _get_paramiko():
    try:
        import paramiko
    except ImportError as exc:
        raise RuntimeError("缺少 paramiko，请先执行：pip install paramiko") from exc
    return paramiko


def _create_ssh_client():
    paramiko = _get_paramiko()
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_options = {
        "hostname": SSH_HOST,
        "port": SSH_PORT,
        "username": SSH_USERNAME,
        "timeout": 20,
        "banner_timeout": 20,
        "auth_timeout": 30,
    }
    if SSH_PASSWORD:
        connect_options["password"] = SSH_PASSWORD
        connect_options["allow_agent"] = False
        connect_options["look_for_keys"] = False
    if SSH_KEY_FILENAME:
        connect_options["key_filename"] = SSH_KEY_FILENAME
    client.connect(**connect_options)
    return client


def run_ssh_command(command):
    """通过 SSH 在 Hadoop 主节点执行命令，失败时抛出异常。"""
    client = _create_ssh_client()
    try:
        stdin, stdout, stderr = client.exec_command(command, get_pty=True)
        del stdin
        stdout_text = stdout.read().decode("utf-8", errors="replace").strip()
        stderr_text = stderr.read().decode("utf-8", errors="replace").strip()
        exit_status = stdout.channel.recv_exit_status()
        result = SSHCommandResult(command, exit_status, stdout_text, stderr_text)
        if not result.success:
            error_message = stderr_text or stdout_text or "未知远程错误"
            raise RuntimeError(f"远程命令执行失败：{error_message}")
        return result
    finally:
        client.close()


def _download_remote_file(remote_path, local_path):
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    client = _create_ssh_client()
    try:
        with client.open_sftp() as sftp:
            sftp.get(remote_path, str(local_path))
    finally:
        client.close()
    return str(local_path)


def _upload_local_file(local_path, remote_path):
    local_path = Path(local_path)
    if not local_path.exists():
        raise FileNotFoundError(f"本地文件不存在：{local_path}")

    client = _create_ssh_client()
    try:
        with client.open_sftp() as sftp:
            sftp.put(str(local_path), remote_path)
    finally:
        client.close()
    return {
        "local_path": str(local_path),
        "remote_path": remote_path,
        "size_bytes": local_path.stat().st_size,
    }


def upload_visitor_csv_to_hdfs_remote():
    """分区模式下检查 MapReduce 输入根目录，不再上传单个总 CSV。"""
    command = " && ".join(
        [
            f"hdfs dfs -test -d {shlex.quote(HDFS_INPUT_PATH)}",
            f"hdfs dfs -ls -R -h {shlex.quote(HDFS_INPUT_PATH)}",
        ]
    )
    command_result = run_ssh_command(f"bash -lc {shlex.quote(command)}")
    return {
        "hdfs_path": HDFS_INPUT_PATH,
        "hdfs_status": command_result.stdout,
        "mode": "date_partition",
    }


def _run_mapreduce_remote(
    jar_name,
    main_class,
    hdfs_output_path,
    result_file_name,
):
    jar_path = f"{REMOTE_HADOOP_DIR}/{jar_name}"
    local_jar_path = LOCAL_HADOOP_DIR / jar_name
    remote_result_path = f"{REMOTE_DATASET_DIR}/{result_file_name}"
    local_result_path = LOCAL_DATASET_DIR / result_file_name

    run_ssh_command(
        " && ".join(
            [
                f"mkdir -p {shlex.quote(REMOTE_HADOOP_DIR)}",
                f"mkdir -p {shlex.quote(REMOTE_DATASET_DIR)}",
            ]
        )
    )
    _upload_local_file(local_jar_path, jar_path)

    command = " && ".join(
        [
            f"hdfs dfs -rm -r -f {shlex.quote(hdfs_output_path)}",
            f"hadoop jar {shlex.quote(jar_path)} {shlex.quote(main_class)} {shlex.quote(HDFS_INPUT_PATH)} {shlex.quote(hdfs_output_path)}",
            f"rm -f {shlex.quote(remote_result_path)}",
            f"hdfs dfs -getmerge {shlex.quote(hdfs_output_path)} {shlex.quote(remote_result_path)}",
        ]
    )
    command_result = run_ssh_command(f"bash -lc {shlex.quote(command)}")
    downloaded_path = _download_remote_file(remote_result_path, local_result_path)
    return {
        "jar": jar_name,
        "main_class": main_class,
        "hdfs_output": hdfs_output_path,
        "remote_result": remote_result_path,
        "local_result": downloaded_path,
        "exit_status": command_result.exit_status,
        "stdout": command_result.stdout,
    }


def run_daily_mapreduce_remote():
    return _run_mapreduce_remote(
        "visitor-daily-count.jar",
        "VisitorDailyCount",
        "/forest/visitor/output/daily",
        "visitor_daily_result.txt",
    )


def run_hourly_mapreduce_remote():
    return _run_mapreduce_remote(
        "visitor-hourly-count.jar",
        "VisitorHourlyCount",
        "/forest/visitor/output/hourly",
        "visitor_hourly_result.txt",
    )


def run_gate_mapreduce_remote():
    return _run_mapreduce_remote(
        "visitor-gate-count.jar",
        "VisitorGateCount",
        "/forest/visitor/output/gate",
        "visitor_gate_result.txt",
    )


def get_peak_warning():
    """根据 MapReduce 统计结果计算峰值小时的客流风险等级。"""
    day_count = VisitorDailyStat.objects.count()
    peak = VisitorHourlyStat.objects.order_by("-total_count", "hour").first()

    if day_count == 0 or peak is None:
        return {
            "level": "none",
            "level_text": "暂无数据",
            "peak_hour": None,
            "peak_total_count": 0,
            "peak_avg_count": 0,
            "peak_ratio": 0,
            "day_count": day_count,
            "advice": "请先运行 MapReduce 统计任务",
        }

    avg_hour_count = (
        VisitorHourlyStat.objects.aggregate(value=Avg("total_count"))["value"] or 0
    )
    peak_avg_count = peak.total_count / day_count
    peak_ratio = peak.total_count / avg_hour_count if avg_hour_count else 0

    if peak_avg_count >= 1800 or peak_ratio >= 1.45:
        level = "danger"
        level_text = "高风险拥挤"
        advice = "建议增加入口疏导人员，开启临时分流通道，并加强高峰时段巡逻"
    elif peak_avg_count >= 1200 or peak_ratio >= 1.25:
        level = "warning"
        level_text = "客流偏高"
        advice = "建议提前安排工作人员在主要入口和热门区域进行秩序维护"
    elif peak_avg_count >= 800 or peak_ratio >= 1.10:
        level = "notice"
        level_text = "客流中等"
        advice = "建议保持常规巡查，关注高峰时段客流变化"
    else:
        level = "normal"
        level_text = "客流正常"
        advice = "当前客流处于正常范围，可按常规管理方案运行"

    next_hour = (peak.hour + 1) % 24
    return {
        "level": level,
        "level_text": level_text,
        "peak_hour": f"{peak.hour:02d}:00-{next_hour:02d}:00",
        "peak_total_count": peak.total_count,
        "peak_avg_count": round(peak_avg_count),
        "peak_ratio": round(peak_ratio, 2),
        "day_count": day_count,
        "advice": advice,
    }
