import os
import paramiko
import shlex
from pathlib import Path
from django.utils import timezone
from django.db import transaction
from django.conf import settings

# =====================
# 配置
# =====================
SSH_HOST = getattr(settings, "HADOOP_SSH_HOST", settings.HDFS_WEB_HOST)
SSH_PORT = getattr(settings, "HADOOP_SSH_PORT", 22)
SSH_USERNAME = getattr(settings, "HADOOP_SSH_USER", settings.HDFS_USER)
SSH_PASSWORD = getattr(settings, "HADOOP_SSH_PASSWORD", "")
SSH_KEY_FILENAME = getattr(settings, "HADOOP_SSH_KEY_FILENAME", "")

REMOTE_HADOOP_DIR = getattr(settings, "HADOOP_REMOTE_DIR", "/root/forest_monitor/hadoop")
REMOTE_DATASET_DIR = getattr(settings, "HADOOP_REMOTE_DATASET_DIR", "/root/forest_monitor/datasets")
HDFS_BASE = getattr(settings, "DEVICE_HDFS_BASE", "/waether/devices")
HDFS_INPUT_DIR = f"{HDFS_BASE}/input"
HDFS_OUTPUT_DIR = f"{HDFS_BASE}/output"
HDFS_FAULT_INPUT = f"{HDFS_INPUT_DIR}/device_fault_log.csv"
HDFS_WORK_INPUT = f"{HDFS_INPUT_DIR}/device_work_log.csv"

LOCAL_DATASET_DIR = Path(settings.BASE_DIR) / "datasets"
LOCAL_HADOOP_DIR = Path(settings.BASE_DIR) / "hadoop"
DEVICE_JAR_NAME = "device-management-mr-1.0-SNAPSHOT.jar"
REMOTE_DEVICE_JAR = f"{REMOTE_HADOOP_DIR}/{DEVICE_JAR_NAME}"


# =====================
# SSH
# =====================
def _create_ssh():
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_options = {
        "hostname": SSH_HOST,
        "port": SSH_PORT,
        "username": SSH_USERNAME,
        "timeout": 30,
        "banner_timeout": 30,
        "auth_timeout": 90,
    }
    if SSH_PASSWORD:
        connect_options["password"] = SSH_PASSWORD
        connect_options["allow_agent"] = False
        connect_options["look_for_keys"] = False
    if SSH_KEY_FILENAME:
        connect_options["key_filename"] = SSH_KEY_FILENAME
    try:
        client.connect(**connect_options)
    except Exception as exc:
        password_status = "已设置" if SSH_PASSWORD else "未设置"
        key_status = SSH_KEY_FILENAME or "未设置"
        raise RuntimeError(
            f"SSH 连接 Hadoop 节点失败：host={SSH_HOST}, port={SSH_PORT}, "
            f"user={SSH_USERNAME}, password={password_status}, key={key_status}. "
            f"原始错误：{exc}"
        ) from exc
    return client


def _upload_local_file(local_path, remote_path):
    local_path = Path(local_path)
    if not local_path.exists():
        raise FileNotFoundError(f"本地文件不存在：{local_path}")

    client = _create_ssh()
    try:
        with client.open_sftp() as sftp:
            sftp.put(str(local_path), remote_path)
    finally:
        client.close()


def _ensure_remote_runtime():
    jar_path = LOCAL_HADOOP_DIR / DEVICE_JAR_NAME
    fault_csv = LOCAL_DATASET_DIR / "device_fault_log.csv"
    work_csv = LOCAL_DATASET_DIR / "device_work_log.csv"

    setup_command = " && ".join(
        [
            f"mkdir -p {shlex.quote(REMOTE_HADOOP_DIR)}",
            f"mkdir -p {shlex.quote(REMOTE_DATASET_DIR)}",
            f"hdfs dfs -mkdir -p {shlex.quote(HDFS_INPUT_DIR)}",
            f"hdfs dfs -mkdir -p {shlex.quote(HDFS_OUTPUT_DIR)}",
        ]
    )
    run_ssh_command(f"bash -lc {shlex.quote(setup_command)}")

    remote_fault_csv = f"{REMOTE_DATASET_DIR}/device_fault_log.csv"
    remote_work_csv = f"{REMOTE_DATASET_DIR}/device_work_log.csv"
    _upload_local_file(jar_path, REMOTE_DEVICE_JAR)
    _upload_local_file(fault_csv, remote_fault_csv)
    _upload_local_file(work_csv, remote_work_csv)

    upload_command = " && ".join(
        [
            f"hdfs dfs -put -f {shlex.quote(remote_fault_csv)} {shlex.quote(HDFS_FAULT_INPUT)}",
            f"hdfs dfs -put -f {shlex.quote(remote_work_csv)} {shlex.quote(HDFS_WORK_INPUT)}",
        ]
    )
    run_ssh_command(f"bash -lc {shlex.quote(upload_command)}")


def run_ssh_command(cmd: str):
    if not cmd.lstrip().startswith("bash -lc "):
        cmd = f"bash -lc {shlex.quote(cmd)}"

    client = _create_ssh()
    try:
        print("EXEC:", cmd)

        stdin, stdout, stderr = client.exec_command(cmd)

        out = stdout.read().decode("utf-8", "ignore")
        err = stderr.read().decode("utf-8", "ignore")
        exit_code = stdout.channel.recv_exit_status()

        print("STDOUT:", out)
        print("STDERR:", err)

        if exit_code != 0:
            raise RuntimeError(f"SSH执行失败: {err or out}")

        return out

    finally:
        client.close()


# =====================
# MR1：故障统计
# =====================
def run_mr1_fault():
    return run_ssh_command(f"""
hdfs dfs -rm -r -f {HDFS_OUTPUT_DIR}/fault;
hadoop jar {REMOTE_DEVICE_JAR} \
main.java.FaultTypeDistribution \
{HDFS_FAULT_INPUT} {HDFS_OUTPUT_DIR}/fault
""")

# =====================
# MR2：健康度
# =====================
def run_mr2_health():
    return run_ssh_command(f"""
hdfs dfs -rm -r -f {HDFS_OUTPUT_DIR}/health;
hadoop jar {REMOTE_DEVICE_JAR} main.java.DeviceHealthAnalysis {HDFS_WORK_INPUT} {HDFS_OUTPUT_DIR}/health
""")

# =====================
# MR3：最差Top10
# =====================
def run_mr3_worst():
    return run_ssh_command(f"""
hdfs dfs -rm -r -f {HDFS_OUTPUT_DIR}/worst;
hadoop jar {REMOTE_DEVICE_JAR} \
main.java.DeviceBottomHealth  \
{HDFS_WORK_INPUT} {HDFS_OUTPUT_DIR}/worst
""")

# =====================
# MR4：7天统计
# =====================
def run_mr4_7day():
    return run_ssh_command(f"""
hdfs dfs -rm -r -f {HDFS_OUTPUT_DIR}/7day;
hadoop jar {REMOTE_DEVICE_JAR} \
main.java.Device7DayAnalysis \
{HDFS_WORK_INPUT} {HDFS_OUTPUT_DIR}/7day
""")

def hdfs_cat(path):
    cmd = f"hdfs dfs -cat {path}"
    return run_ssh_command(cmd)

@transaction.atomic
def load_fault_to_mysql():
    from .models import FaultTypeDistribution
    from django.utils import timezone

    output = hdfs_cat(f"{HDFS_OUTPUT_DIR}/fault/part-r-00000")

    FaultTypeDistribution.objects.all().delete()

    if not output:
        print("FAULT EMPTY")
        return

    for line in output.split("\n"):
        parts = line.split("\t")
        if len(parts) < 2:
            continue

        FaultTypeDistribution.objects.create(
            fault_type=parts[0],
            fault_count=int(float(parts[1])),
            analysis_date=timezone.now().date()
        )

@transaction.atomic
def load_health_to_mysql():
    from .models import DeviceHealthAnalysis, Device
    from django.utils import timezone

    output = hdfs_cat(f"{HDFS_OUTPUT_DIR}/health/part-r-00000")

    DeviceHealthAnalysis.objects.all().delete()

    for line in output.split("\n"):
        if not line.strip():
            continue

        parts = line.split("\t")
        if len(parts) < 2:
            continue

        device_id = parts[0].strip()
        score = float(parts[1])

        try:
            device = Device.objects.get(device_id=device_id)
        except Device.DoesNotExist:
            print(f"[SKIP] device not found: {device_id}")
            continue

        DeviceHealthAnalysis.objects.create(
            device=device,
            health_score=score,
            analysis_date=timezone.now().date()
        )

@transaction.atomic
def load_worst_to_mysql():
    from .models import DeviceWorstHealth, Device
    from django.utils import timezone

    output = hdfs_cat(f"{HDFS_OUTPUT_DIR}/worst/part-r-00000")

    DeviceWorstHealth.objects.all().delete()

    if not output:
        print("WORST EMPTY")
        return

    rank = 1

    for line in output.split("\n"):
        parts = line.split("\t")
        if len(parts) < 3:
            continue

        device_id = parts[1].strip()
        score = float(parts[2])

        try:
            device = Device.objects.get(device_id=device_id)
        except Device.DoesNotExist:
            print(f"[SKIP] device not found: {parts[1]}")
            continue
        except Exception as e:
            print(f"[ERROR] 解析或入库失败: {e}, 原始行: {line}")
            continue

        DeviceWorstHealth.objects.create(
            rank_id=rank,
            device=device,
            health_score=score,
            analysis_date=timezone.now().date()
        )

        rank += 1

@transaction.atomic
def load_7day_to_mysql():
    from .models import Device, Device7DayAnalysis
    from django.utils import timezone

    output = hdfs_cat(f"{HDFS_OUTPUT_DIR}/7day/part-*")

    Device7DayAnalysis.objects.all().delete()

    # 提前获取当前日期，避免在循环中重复调用
    current_date = timezone.now().date()

    for line in output.split("\n"):
        parts = line.split("\t")

        # 【核心修复 1】实际输出只有 6 列，改为 < 6
        if len(parts) < 6:
            continue

        try:
            device = Device.objects.get(device_id=parts[0])
        except Device.DoesNotExist:
            print(f"[SKIP] device not found: {parts[0]}")
            continue

        try:
            Device7DayAnalysis.objects.create(
                device=device,
                stat_date=current_date,
                # 【核心修复 2】索引全部向前移一位，从 parts[1] 开始
                avg_cpu=float(parts[1]),
                avg_memory=float(parts[2]),
                avg_temperature=float(parts[3]),
                avg_power=float(parts[4]),
                avg_network_delay=float(parts[5]),
                health_score=0,
                analysis_date=current_date
            )
        except Exception as e:
            print(f"[ERROR] 7day create failed for {parts[0]}: {e}")
# =====================
# Pipeline
# =====================
def run_device_full_pipeline():
    print("===== START DEVICE PIPELINE 2=====")

    _ensure_remote_runtime()

    run_mr1_fault()
    run_mr2_health()
    run_mr3_worst()
    run_mr4_7day()

    print("===== MR DONE =====")

    load_fault_to_mysql()
    load_health_to_mysql()
    load_worst_to_mysql()
    load_7day_to_mysql()

    print("===== MYSQL DONE =====")

    return {"status": "ok"}
