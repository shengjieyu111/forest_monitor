import os
import paramiko
from pathlib import Path
from django.utils import timezone
from django.db import transaction
from django.conf import settings

# =====================
# 配置
# =====================
SSH_HOST = os.getenv("HADOOP_SSH_HOST", "192.168.10.11")
SSH_PORT = 22
SSH_USERNAME = "hxh"
SSH_PASSWORD = "123456"

REMOTE_HADOOP_DIR = "/home/hxh/forest_monitor/devices"
HDFS_BASE = "/hxh/forest_monitor/hadoop/devices"
HDFS_INPUT_DIR = f"{HDFS_BASE}/input"
HDFS_OUTPUT_DIR = f"{HDFS_BASE}/output"
HDFS_FAULT_INPUT = f"{HDFS_INPUT_DIR}/device_fault_log.csv"
HDFS_WORK_INPUT = f"{HDFS_INPUT_DIR}/device_work_log.csv"

LOCAL_DATASET_DIR = Path(settings.BASE_DIR) / "datasets"


# =====================
# SSH
# =====================
def _create_ssh():
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


def run_ssh_command(cmd: str):
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
hadoop jar {REMOTE_HADOOP_DIR}/device-management-mr-1.0-SNAPSHOT.jar \
main.java.FaultTypeDistribution \
{HDFS_FAULT_INPUT} {HDFS_OUTPUT_DIR}/fault
""")

# =====================
# MR2：健康度
# =====================
def run_mr2_health():
    return run_ssh_command(f"""
hdfs dfs -rm -r -f {HDFS_OUTPUT_DIR}/health;
hadoop jar {REMOTE_HADOOP_DIR}/device-management-mr-1.0-SNAPSHOT.jar main.java.DeviceHealthAnalysis {HDFS_WORK_INPUT} {HDFS_OUTPUT_DIR}/health
""")

# =====================
# MR3：最差Top10
# =====================
def run_mr3_worst():
    return run_ssh_command(f"""
hdfs dfs -rm -r -f {HDFS_OUTPUT_DIR}/worst;
hadoop jar {REMOTE_HADOOP_DIR}/device-management-mr-1.0-SNAPSHOT.jar \
main.java.DeviceBottomHealth  \
{HDFS_WORK_INPUT} {HDFS_OUTPUT_DIR}/worst
""")

# =====================
# MR4：7天统计
# =====================
def run_mr4_7day():
    return run_ssh_command(f"""
hdfs dfs -rm -r -f {HDFS_OUTPUT_DIR}/7day;
hadoop jar {REMOTE_HADOOP_DIR}/device-management-mr-1.0-SNAPSHOT.jar \
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