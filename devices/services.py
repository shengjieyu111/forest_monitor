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
HDFS_INFO_INPUT = f"{HDFS_INPUT_DIR}/devices_info.csv"
HDFS_FAULT_INPUT = f"{HDFS_INPUT_DIR}/devices_fault_log.csv"
HDFS_WORK_INPUT = f"{HDFS_INPUT_DIR}/devices_work_log.csv"

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
hdfs dfs -rm -r -f {HDFS_OUTPUT_DIR}/fault {HDFS_OUTPUT_DIR}/fault_temp_join;
hadoop jar {REMOTE_HADOOP_DIR}/device-management-mr-1.0-SNAPSHOT.jar \
main.java.FaultTypeDistribution \
{HDFS_FAULT_INPUT} \
{HDFS_INFO_INPUT} \
{HDFS_OUTPUT_DIR}/fault
""")

# =====================
# MR2：健康度
# =====================
def run_mr2_health():
    return run_ssh_command(f"""
hdfs dfs -rm -r -f {HDFS_OUTPUT_DIR}/health;
hadoop jar {REMOTE_HADOOP_DIR}/device-management-mr-1.0-SNAPSHOT.jar \
main.java.DeviceHealthAnalysis \
{HDFS_WORK_INPUT} \
{HDFS_OUTPUT_DIR}/health
""")

# =====================
# MR3：时区分析
# =====================
def run_mr3_location():
    return run_ssh_command(f"""
hdfs dfs -rm -r -f {HDFS_OUTPUT_DIR}/location {HDFS_OUTPUT_DIR}/location_temp_join;
hadoop jar {REMOTE_HADOOP_DIR}/device-management-mr-1.0-SNAPSHOT.jar \
main.java.FaultByLocation \
{HDFS_FAULT_INPUT} \
{HDFS_INFO_INPUT} \
{HDFS_OUTPUT_DIR}/location
""")

# =====================
# MR4：工作统计
# =====================
def run_mr4_work():
    return run_ssh_command(f"""
hdfs dfs -rm -r -f {HDFS_OUTPUT_DIR}/work;
hadoop jar {REMOTE_HADOOP_DIR}/device-management-mr-1.0-SNAPSHOT.jar \
main.java.DeviceWorkAnalysis \
{HDFS_WORK_INPUT} \
{HDFS_OUTPUT_DIR}/work
""")

def hdfs_cat(path):
    cmd = f"hdfs dfs -cat {path}"
    return run_ssh_command(cmd)


@transaction.atomic
def load_fault_to_mysql():
    from .models import FaultTypeDistribution
    from django.utils import timezone
    from django.db import transaction as db_transaction

    output = hdfs_cat(f"{HDFS_OUTPUT_DIR}/fault/part-r-00000")
    FaultTypeDistribution.objects.all().delete()

    if not output:
        print("FAULT EMPTY")
        return

    success_count = 0
    skip_count = 0

    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) != 2:
            print(f"[SKIP] 格式错误(非2列): {line}")
            skip_count += 1
            continue

        try:
            fault_count = int(parts[1])
            raw_key = parts[0]

            # 解析复合Key：FAULT_TYPE_DEVICE_TYPE
            if raw_key.endswith("_CAMERA"):
                device_type = "CAMERA"
                fault_type = raw_key[:-7]  # 去掉末尾的 _CAMERA
            elif raw_key.endswith("_SENSOR"):
                device_type = "SENSOR"
                fault_type = raw_key[:-7]  # 去掉末尾的 _SENSOR
            else:
                # 如果以后增加新设备类型，从最后一个下划线切开
                last_underscore_idx = raw_key.rfind("_")
                if last_underscore_idx == -1:
                    print(f"[SKIP] 无法解析设备类型: {line}")
                    skip_count += 1
                    continue
                device_type = raw_key[last_underscore_idx + 1:]
                fault_type = raw_key[:last_underscore_idx]

            FaultTypeDistribution.objects.create(
                fault_type=fault_type,
                device_type=device_type,
                fault_count=fault_count,
                analysis_date=timezone.now().date()
            )
            success_count += 1

        except Exception as e:
            # 如果某条数据报错，回滚当前事务，继续处理下一条
            db_transaction.rollback()
            print(f"[SKIP] 解析或插入失败: {line}, 错误: {e}")
            skip_count += 1
            continue

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


from django.db import transaction


@transaction.atomic
def load_fault_time_region_to_mysql():
    from .models import FaultTimeRegionAnalysis
    from django.utils import timezone

    output = hdfs_cat(f"{HDFS_OUTPUT_DIR}/location/part-r-00000")
    # 清空旧数据
    FaultTimeRegionAnalysis.objects.all().delete()

    if not output:
        print("FAULT TIME REGION EMPTY")
        return

    success_count = 0
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) != 2:
            print(f"[SKIP] 格式错误(非2列): {line}")
            continue

        try:
            raw_key = parts[0].strip()
            fault_count = int(parts[1].strip())

            # 第一步：用 | 切割，分出 (区域_月份) 和 (故障类型)
            time_fault_parts = raw_key.split("|")
            if len(time_fault_parts) != 2:
                print(f"[SKIP] 缺少 | 分隔符: {line}")
                continue

            location_month_str = time_fault_parts[0]  # CORE_SCENIC_2026-03
            fault_type = time_fault_parts[1]  # CPU_SPIKE

            # 第二步：用 _ 切割，分出 (区域) 和 (月份)
            # 区域名有下划线，需要用 rsplit('_', 1) 从右边切
            location_parts = location_month_str.rsplit("_", 1)
            if len(location_parts) != 2:
                print(f"[SKIP] 无法解析区域和月份: {line}")
                continue

            location = location_parts[0]  # CORE_SCENIC
            month_str = location_parts[1]  # 2026-03

            # 将月份字符串转换为 date 对象 (补全为当月1号)
            analysis_date = timezone.datetime.strptime(f"{month_str}-01", "%Y-%m-%d").date()

            FaultTimeRegionAnalysis.objects.create(
                analysis_date=analysis_date,
                location=location,
                fault_type=fault_type,
                fault_count=fault_count,
            )
            success_count += 1

        except Exception as e:
            # 捕获所有异常，保证单条数据失败不影响整体事务
            print(f"[SKIP] Parse or insert error for line: {line}, Error: {e}")
            continue

@transaction.atomic
def load_work_to_mysql():
    from .models import Device, DeviceWorkAnalysis
    from django.utils import timezone

    output = hdfs_cat(f"{HDFS_OUTPUT_DIR}/work/part-r-00000")

    DeviceWorkAnalysis.objects.all().delete()

    # 提前获取当前日期，避免在循环中重复调用
    current_date = timezone.now().date()

    for line in output.split("\n"):
        parts = line.split("\t")

        if len(parts) < 6:
            continue

        try:
            device = Device.objects.get(device_id=parts[0])
        except Device.DoesNotExist:
            print(f"[SKIP] device not found: {parts[0]}")
            continue

        try:
            DeviceWorkAnalysis.objects.create(
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
            print(f"[ERROR] work create failed for {parts[0]}: {e}")

# =====================
# Pipeline
# =====================
def run_device_full_pipeline():
    print("===== START DEVICE PIPELINE 2=====")

    run_mr1_fault()
    run_mr2_health()
    run_mr3_location()
    run_mr4_work()

    print("===== MR DONE =====")

    load_fault_to_mysql()
    load_health_to_mysql()
    load_fault_time_region_to_mysql()
    load_work_to_mysql()

    print("===== MYSQL DONE =====")

    return {"status": "ok"}