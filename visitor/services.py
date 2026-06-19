import os
import shlex
import paramiko
from datetime import datetime, time, timedelta
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

# =====================
# 1. 配置
# =====================
SSH_HOST = os.getenv("HADOOP_SSH_HOST", "192.168.10.11")
SSH_PORT = 22
SSH_USERNAME = "hxh"
SSH_PASSWORD = "123456"

# 远程服务器上的路径
REMOTE_HADOOP_DIR = "/home/hxh/forest_monitor/visitors"
REMOTE_DATASET_DIR = "/home/hxh/forest_monitor/visitors/input"

# HDFS 上的路径
HDFS_INPUT_PATH = "/hxh/forest_monitor/hadoop/visitors/input"
HDFS_OUTPUT_BASE = "/hxh/forest_monitor/hadoop/visitors/output"
HDFS_DAILY_OUTPUT = f"{HDFS_OUTPUT_BASE}/daily"
HDFS_HOURLY_OUTPUT = f"{HDFS_OUTPUT_BASE}/hourly"
HDFS_GATE_OUTPUT = f"{HDFS_OUTPUT_BASE}/gate"

# 本地路径（不再用于存放 JAR 包）
LOCAL_HADOOP_DIR = Path(settings.BASE_DIR) / "hadoop"


# =====================
# 2. SSH 核心工具
# =====================
def _create_ssh_client():
    """创建并返回一个 SSH 客户端连接"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=SSH_HOST,
        port=SSH_PORT,
        username=SSH_USERNAME,
        password=SSH_PASSWORD,
        timeout=15,
    )
    return client


def run_ssh_command(command: str):
    """在远程 Hadoop 服务器上执行命令"""
    client = _create_ssh_client()
    try:
        print(f"[SSH EXEC] {command}")
        stdin, stdout, stderr = client.exec_command(command, get_pty=True)
        stdout_text = stdout.read().decode("utf-8", errors="replace").strip()
        stderr_text = stderr.read().decode("utf-8", errors="replace").strip()
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            error_message = stderr_text or stdout_text or "未知远程错误"
            raise RuntimeError(f"远程命令执行失败: {error_message}")
        return stdout_text
    finally:
        client.close()


def hdfs_cat(path):
    """读取 HDFS 上的文件内容"""
    cmd = f"hdfs dfs -cat {path}"
    return run_ssh_command(cmd)


# _upload_local_file 函数已不再需要，可以删除

# =====================
# 3. 内部 MapReduce 执行逻辑
# =====================
def _run_mapreduce_remote(jar_name, main_class, hdfs_output_path):
    """通用的 MapReduce 任务执行函数"""
    # 1. 定义远程 JAR 包的完整路径
    remote_jar_path = f"{REMOTE_HADOOP_DIR}/{jar_name}"

    # 2. 构建执行命令
    # 先强制删除 HDFS 输出目录，再执行 hadoop jar 命令
    command = " && ".join([
        f"hdfs dfs -rm -r -f {shlex.quote(hdfs_output_path)}",
        f"hadoop jar {shlex.quote(remote_jar_path)} {shlex.quote(main_class)} {shlex.quote(HDFS_INPUT_PATH)} {shlex.quote(hdfs_output_path)}"
    ])

    # 3. 执行命令
    return run_ssh_command(f"bash -lc {shlex.quote(command)}")


# =====================
# 4. 对外暴露的接口（严格保留原函数名）
# =====================
def import_local_date_partitions():
    """
    原函数名：import_local_date_partitions
    修改说明：保留原函数名，内部逻辑改为通过 SSH 检查 HDFS 目录状态
    """
    try:
        output = run_ssh_command(f"hdfs dfs -ls {HDFS_INPUT_PATH}")
        return {
            "hdfs_path": HDFS_INPUT_PATH,
            "hdfs_status": output,
            "mode": "date_partition"
        }
    except Exception as e:
        raise RuntimeError(f"检查 HDFS 分区失败: {str(e)}")


def import_visitor_records():
    """
    原函数名：import_visitor_records
    修改说明：保留原函数名。由于现在由 Hadoop 直接处理原始数据，
    此函数作为流程占位符，返回跳过状态，避免破坏上层调用逻辑。
    """
    return {
        "skipped": True,
        "existing_rows": 0,
        "detail": "原始数据由 Hadoop MapReduce 直接处理，无需 Django 导入。"
    }


def run_daily_mapreduce():
    """
    原函数名：run_daily_mapreduce
    修改说明：内部调用 SSH 执行每日统计的 MapReduce 任务
    """
    return _run_mapreduce_remote(
        "visitor-daily-count.jar",
        "VisitorDailyCount",
        HDFS_DAILY_OUTPUT
    )


def run_hourly_mapreduce():
    """
    原函数名：run_hourly_mapreduce
    修改说明：内部调用 SSH 执行每小时统计的 MapReduce 任务
    """
    return _run_mapreduce_remote(
        "visitor-hourly-count.jar",
        "VisitorHourlyCount",
        HDFS_HOURLY_OUTPUT
    )


def run_gate_mapreduce():
    """
    原函数名：run_gate_mapreduce
    修改说明：内部调用 SSH 执行各闸口统计的 MapReduce 任务
    """
    return _run_mapreduce_remote(
        "visitor-gate-count.jar",
        "VisitorGateCount",
        HDFS_GATE_OUTPUT
    )


@transaction.atomic
def import_daily_result():
    """
    原函数名：import_daily_result
    修改说明：从 HDFS 读取每日统计结果并导入数据库
    """
    output = hdfs_cat(f"{HDFS_DAILY_OUTPUT}/part-r-00000")
    VisitorDailyStat.objects.all().delete()
    if not output:
        print("DAILY RESULT EMPTY")
        return
    stats = []
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            print(f"[SKIP] 格式错误: {line}")
            continue
        try:
            stat_date = datetime.strptime(parts[0], "%Y-%m-%d").date()
            total_count = int(parts[1])
            stats.append(VisitorDailyStat(stat_date=stat_date, total_count=total_count))
        except Exception as e:
            print(f"[SKIP] 解析失败: {line}, 错误: {e}")
            continue
    VisitorDailyStat.objects.bulk_create(stats, batch_size=1000)
    return len(stats)


@transaction.atomic
def import_hourly_result():
    """
    原函数名：import_hourly_result
    修改说明：从 HDFS 读取每小时统计结果并导入数据库
    """
    output = hdfs_cat(f"{HDFS_HOURLY_OUTPUT}/part-r-00000")
    VisitorHourlyStat.objects.all().delete()
    if not output:
        print("HOURLY RESULT EMPTY")
        return
    stats = []
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            print(f"[SKIP] 格式错误: {line}")
            continue
        try:
            hour = int(parts[0])
            total_count = int(parts[1])
            stats.append(VisitorHourlyStat(hour=hour, total_count=total_count))
        except Exception as e:
            print(f"[SKIP] 解析失败: {line}, 错误: {e}")
            continue
    VisitorHourlyStat.objects.bulk_create(stats, batch_size=1000)
    return len(stats)


@transaction.atomic
def import_gate_result():
    """
    原函数名：import_gate_result
    修改说明：从 HDFS 读取各闸口统计结果并导入数据库
    """
    output = hdfs_cat(f"{HDFS_GATE_OUTPUT}/part-r-00000")
    VisitorGateStat.objects.all().delete()
    if not output:
        print("GATE RESULT EMPTY")
        return
    stats = []
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            print(f"[SKIP] 格式错误: {line}")
            continue
        try:
            gate = parts[0]
            total_count = int(parts[1])
            stats.append(VisitorGateStat(gate=gate, total_count=total_count))
        except Exception as e:
            print(f"[SKIP] 解析失败: {line}, 错误: {e}")
            continue
    VisitorGateStat.objects.bulk_create(stats, batch_size=1000)
    return len(stats)


def get_peak_warning():
    """根据统计结果计算峰值小时的客流风险等级"""
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
    avg_hour_count = (VisitorHourlyStat.objects.aggregate(value=Avg("total_count"))["value"] or 0)
    peak_avg_count = peak.total_count / day_count
    peak_ratio = peak.total_count / avg_hour_count if avg_hour_count else 0
    if peak_avg_count >= 1800 or peak_ratio >= 1.45:
        level, level_text = "danger", "高风险拥挤"
        advice = "建议增加入口疏导人员，开启临时分流通道，并加强高峰时段巡逻"
    elif peak_avg_count >= 1200 or peak_ratio >= 1.25:
        level, level_text = "warning", "客流偏高"
        advice = "建议提前安排工作人员在主要入口和热门区域进行秩序维护"
    elif peak_avg_count >= 800 or peak_ratio >= 1.10:
        level, level_text = "notice", "客流中等"
        advice = "建议保持常规巡查，关注高峰时段客流变化"
    else:
        level, level_text = "normal", "客流正常"
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


def run_visitor_full_pipeline():
    """
    执行完整的游客数据分析流水线
    """
    print("===== START VISITOR PIPELINE =====")
    # --- 执行 MapReduce ---
    run_daily_mapreduce()
    run_hourly_mapreduce()
    run_gate_mapreduce()
    print("===== MR DONE =====")
    # --- 导入 MySQL ---
    import_daily_result()
    import_hourly_result()
    import_gate_result()
    print("===== MYSQL DONE =====")
    # --- 生成报告 ---
    report = get_peak_warning()
    return {"status": "ok", "report": report}