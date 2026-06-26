import os
import shlex
from datetime import datetime
from pathlib import Path

import paramiko
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from .models import (
    DailyComfortStat,
    DailyRiskStat,
    DailyWeatherStat,
    HourlyWeatherProfile,
    MapReduceSyncLog,
    TopRiskDay,
)

# =====================
# 1. 配置
# =====================
SSH_HOST = os.getenv("HADOOP_SSH_HOST", "192.168.56.100")
SSH_PORT = int(os.getenv("HADOOP_SSH_PORT", "22"))
SSH_USERNAME = os.getenv("HADOOP_SSH_USERNAME", "root")
SSH_PASSWORD = os.getenv("HADOOP_SSH_PASSWORD", "")

REMOTE_HADOOP_DIR = os.getenv(
    "HADOOP_REMOTE_WEATHER_DIR", "/root/forest_monitor/weather"
)
REMOTE_DATASET_DIR = os.getenv(
    "HADOOP_REMOTE_WEATHER_INPUT_DIR", "/root/forest_monitor/weather/input"
)

HDFS_BASE = os.getenv("HDFS_WEATHER_BASE", "/forest/weather")
HDFS_INPUT_DIR = f"{HDFS_BASE}/input"
HDFS_OUTPUT_DIR = f"{HDFS_BASE}/output"

LOCAL_DATASET_DIR = Path(settings.BASE_DIR) / "datasets"
WEATHER_CSV_PATH = LOCAL_DATASET_DIR / "weather_15days.csv"

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


def run_ssh_command(command: str, timeout=120):
    """在远程 Hadoop 服务器上执行命令"""
    client = _create_ssh_client()
    try:
        print(f"[SSH EXEC] {command}")
        stdin, stdout, stderr = client.exec_command(command, get_pty=True)

        # 设置命令执行超时
        stdout.channel.settimeout(timeout)
        stderr.channel.settimeout(timeout)

        stdout_text = stdout.read().decode("utf-8", errors="replace").strip()
        stderr_text = stderr.read().decode("utf-8", errors="replace").strip()
        exit_status = stdout.channel.recv_exit_status()

        print(f"[SSH EXIT] status={exit_status}")
        if stdout_text:
            print(f"[SSH STDOUT] {stdout_text[:500]}")

        if exit_status != 0:
            error_message = stderr_text or stdout_text or "未知远程错误"
            print(f"[SSH ERROR] {error_message[:500]}")
            raise RuntimeError(f"远程命令执行失败 (exit={exit_status}): {error_message}")
        return stdout_text
    except Exception as e:
        print(f"[SSH EXCEPTION] {type(e).__name__}: {str(e)}")
        raise
    finally:
        client.close()


def hdfs_cat(path):
    """读取 HDFS 上的文件内容"""
    cmd = f"hdfs dfs -cat {path}"
    try:
        return run_ssh_command(cmd)
    except RuntimeError as e:
        error_msg = str(e)
        # 如果是文件不存在，友好处理
        if "No such file" in error_msg or "non-existent" in error_msg.lower():
            print(f"[WARN] HDFS文件不存在: {path}")
            return ""
        raise


# =====================
# 3. 上传 CSV 到 HDFS（设备模块没有此步骤，保留空函数）
# =====================
def upload_csv_to_hdfs():
    """
    设备模块没有上传步骤，假设CSV已在HDFS上
    此函数保留以匹配pipeline调用，不做任何操作
    """
    return {"status": "skipped", "message": "CSV已在HDFS上"}


# =====================
# 4. MapReduce 执行逻辑
# =====================
def _run_weather_mr(jar_name, main_class, hdfs_output_path):
    """通用的气象 MapReduce 任务执行函数"""
    # JAR文件完整路径
    remote_jar_path = f"{REMOTE_HADOOP_DIR}/{jar_name}"
    # 输入为完整CSV文件路径
    hdfs_input_file = f"{HDFS_INPUT_DIR}/weather_15days.csv"

    # 构建执行命令
    command = " && ".join([
        f"hdfs dfs -rm -r -f {shlex.quote(hdfs_output_path)}",
        f"hadoop jar {shlex.quote(remote_jar_path)} {shlex.quote(main_class)} {shlex.quote(hdfs_input_file)} {shlex.quote(hdfs_output_path)}"
    ])

    print(f"[MR START] {main_class} -> {hdfs_output_path}")
    result = run_ssh_command(f"bash -lc {shlex.quote(command)}", timeout=300)
    print(f"[MR DONE] {main_class}")
    return result


def run_mr_weather_stats():
    """MR1: 每日气象统计"""
    return _run_weather_mr(
        "weather-management-mr-1.0-SNAPSHOT.jar",
        "main.java.WeatherStatsMR",
        f"{HDFS_OUTPUT_DIR}/stats"
    )


def run_mr_hourly_profile():
    """MR2: 小时气象分布"""
    return _run_weather_mr(
        "weather-management-mr-1.0-SNAPSHOT.jar",
        "main.java.WeatherHourlyProfileMR",
        f"{HDFS_OUTPUT_DIR}/hourly"
    )


def run_mr_daily_comfort():
    """MR3: 每日舒适度统计"""
    return _run_weather_mr(
        "weather-management-mr-1.0-SNAPSHOT.jar",
        "main.java.WeatherDailyComfortMR",
        f"{HDFS_OUTPUT_DIR}/comfort"
    )


def run_mr_daily_risk():
    """MR4: 每日风险统计"""
    return _run_weather_mr(
        "weather-management-mr-1.0-SNAPSHOT.jar",
        "main.java.WeatherDailyRiskMR",
        f"{HDFS_OUTPUT_DIR}/risk"
    )


def run_mr_risk_topn():
    """MR5: 风险日 TopN 排名"""
    return _run_weather_mr(
        "weather-management-mr-1.0-SNAPSHOT.jar",
        "main.java.WeatherRiskTopNMR",
        f"{HDFS_OUTPUT_DIR}/topn"
    )


# =====================
# 5. 解析 HDFS 输出
# =====================
def _parse_kv_line(value_part: str):
    """解析 key=value,key=value 格式"""
    if not value_part:
        return {}
    result = {}
    for item in value_part.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            key = k.strip()
            val = v.strip()
            # 处理可能的空值
            if val and val.lower() not in ('none', 'null', ''):
                result[key] = val
    return result


def _safe_decimal(value, default=0):
    """安全转换为Decimal"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_int(value, default=0):
    """安全转换为整数"""
    if value is None:
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


# =====================
# 6. 导入 MySQL
# =====================
@transaction.atomic
def load_weather_stats_to_mysql():
    """从 HDFS 导入每日气象统计到 MySQL"""
    output = hdfs_cat(f"{HDFS_OUTPUT_DIR}/stats/part-r-00000")
    DailyWeatherStat.objects.all().delete()
    if not output:
        print("[SKIP] WEATHER STATS EMPTY")
        return 0

    stats = []
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            print(f"[SKIP] 格式错误(非2列): {line}")
            continue
        try:
            date_str = parts[0].strip()
            values = _parse_kv_line(parts[1])
            # 获取预警信息，确保不为空
            risk_warning = values.get("risk_warning") or "正常"
            stats.append(DailyWeatherStat(
                date=datetime.strptime(date_str, "%Y-%m-%d").date(),
                temperature_avg=_safe_decimal(values.get("temp_avg"), 0),
                temperature_peak=_safe_decimal(values.get("temp_peak"), 0),
                humidity_avg=_safe_decimal(values.get("humidity_avg"), 0),
                humidity_peak=_safe_decimal(values.get("humidity_peak"), 0),
                pm25_avg=_safe_decimal(values.get("pm25_avg"), 0),
                pm25_peak=_safe_decimal(values.get("pm25_peak"), 0),
                illumination_avg=_safe_decimal(values.get("illumination_avg"), 0),
                illumination_peak=_safe_decimal(values.get("illumination_peak"), 0),
                risk_warning=risk_warning,
            ))
        except Exception as e:
            print(f"[SKIP] 解析失败: {line}, 错误: {e}")
            continue

    DailyWeatherStat.objects.bulk_create(stats, batch_size=1000)
    print(f"[OK] 加载 {len(stats)} 条气象统计数据")
    return len(stats)


@transaction.atomic
def load_hourly_profile_to_mysql():
    """从 HDFS 导入小时气象分布到 MySQL"""
    output = hdfs_cat(f"{HDFS_OUTPUT_DIR}/hourly/part-r-00000")
    HourlyWeatherProfile.objects.all().delete()
    if not output:
        print("[SKIP] HOURLY PROFILE EMPTY")
        return 0

    stats = []
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            print(f"[SKIP] 格式错误(非2列): {line}")
            continue
        try:
            hour = int(parts[0].strip())
            values = _parse_kv_line(parts[1])
            stats.append(HourlyWeatherProfile(
                hour=hour,
                sample_count=_safe_int(values.get("sample_count"), 0),
                temperature_avg=_safe_decimal(values.get("temp_avg"), 0),
                humidity_avg=_safe_decimal(values.get("humidity_avg"), 0),
                pm25_avg=_safe_decimal(values.get("pm25_avg"), 0),
                illumination_avg=_safe_decimal(values.get("illumination_avg"), 0),
            ))
        except Exception as e:
            print(f"[SKIP] 解析失败: {line}, 错误: {e}")
            continue

    HourlyWeatherProfile.objects.bulk_create(stats, batch_size=1000)
    print(f"[OK] 加载 {len(stats)} 条小时分布数据")
    return len(stats)


@transaction.atomic
def load_comfort_to_mysql():
    """从 HDFS 导入舒适度统计到 MySQL"""
    output = hdfs_cat(f"{HDFS_OUTPUT_DIR}/comfort/part-r-00000")
    DailyComfortStat.objects.all().delete()
    if not output:
        print("[SKIP] COMFORT STATS EMPTY")
        return 0

    stats = []
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            print(f"[SKIP] 格式错误(非2列): {line}")
            continue
        try:
            date_str = parts[0].strip()
            values = _parse_kv_line(parts[1])
            stats.append(DailyComfortStat(
                date=datetime.strptime(date_str, "%Y-%m-%d").date(),
                sample_count=_safe_int(values.get("sample_count"), 0),
                comfort_index_avg=_safe_decimal(values.get("comfort_index_avg"), 0),
                comfortable_count=_safe_int(values.get("comfortable_count"), 0),
                attention_count=_safe_int(values.get("attention_count"), 0),
                uncomfortable_count=_safe_int(values.get("uncomfortable_count"), 0),
                comfort_rate=_safe_decimal(values.get("comfort_rate"), 0),
            ))
        except Exception as e:
            print(f"[SKIP] 解析失败: {line}, 错误: {e}")
            continue

    DailyComfortStat.objects.bulk_create(stats, batch_size=1000)
    print(f"[OK] 加载 {len(stats)} 条舒适度统计数据")
    return len(stats)


@transaction.atomic
def load_risk_to_mysql():
    """从 HDFS 导入风险统计到 MySQL"""
    output = hdfs_cat(f"{HDFS_OUTPUT_DIR}/risk/part-r-00000")
    DailyRiskStat.objects.all().delete()
    if not output:
        print("[SKIP] RISK STATS EMPTY")
        return 0

    stats = []
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            print(f"[SKIP] 格式错误(非2列): {line}")
            continue
        try:
            date_str = parts[0].strip()
            values = _parse_kv_line(parts[1])
            stats.append(DailyRiskStat(
                date=datetime.strptime(date_str, "%Y-%m-%d").date(),
                sample_count=_safe_int(values.get("sample_count"), 0),
                high_temp_count=_safe_int(values.get("high_temp_count"), 0),
                high_humidity_count=_safe_int(values.get("high_humidity_count"), 0),
                pollution_count=_safe_int(values.get("pollution_count"), 0),
                fire_risk_count=_safe_int(values.get("fire_risk_count"), 0),
                normal_count=_safe_int(values.get("normal_count"), 0),
                risk_rate=_safe_decimal(values.get("risk_rate"), 0),
            ))
        except Exception as e:
            print(f"[SKIP] 解析失败: {line}, 错误: {e}")
            continue

    DailyRiskStat.objects.bulk_create(stats, batch_size=1000)
    print(f"[OK] 加载 {len(stats)} 条风险统计数据")
    return len(stats)


@transaction.atomic
def load_topn_to_mysql():
    """从 HDFS 导入风险 TopN 排名到 MySQL"""
    output = hdfs_cat(f"{HDFS_OUTPUT_DIR}/topn/part-r-00000")
    TopRiskDay.objects.all().delete()
    if not output:
        print("[SKIP] TOPN EMPTY")
        return 0

    stats = []
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            print(f"[SKIP] 格式错误(非2列): {line}")
            continue
        try:
            rank = int(parts[0].strip())
            values = _parse_kv_line(parts[1])
            # 解析日期，尝试多种格式
            date_str = values.get("date", "1970-01-01")
            try:
                parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                parsed_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            stats.append(TopRiskDay(
                rank=rank,
                date=parsed_date,
                risk_score=_safe_decimal(values.get("risk_score"), 0),
                dangerous_count=_safe_int(values.get("dangerous_count"), 0),
                temperature_peak=_safe_decimal(values.get("temp_peak"), 0),
                humidity_low=_safe_decimal(values.get("humidity_low"), 0),
                pm25_peak=_safe_decimal(values.get("pm25_peak"), 0),
                illumination_peak=_safe_decimal(values.get("illumination_peak"), 0),
            ))
        except Exception as e:
            print(f"[SKIP] 解析失败: {line}, 错误: {e}")
            continue

    TopRiskDay.objects.bulk_create(stats, batch_size=1000)
    print(f"[OK] 加载 {len(stats)} 条风险TopN数据")
    return len(stats)


# =====================
# 7. 健康评分计算
# =====================
def get_weather_health_summary():
    """根据数据库统计结果计算气象健康摘要"""
    daily_count = DailyWeatherStat.objects.count()
    risk_count = DailyRiskStat.objects.count()
    comfort_count = DailyComfortStat.objects.count()

    if daily_count == 0:
        return {
            "level": "none",
            "level_text": "暂无数据",
            "health_score": None,
            "average_risk_rate": 0,
            "average_comfort_rate": 0,
            "advice": "请先运行 MapReduce 统计任务",
        }

    avg_risk_rate = DailyRiskStat.objects.aggregate(
        avg=models.Avg("risk_rate")
    )["avg"] or 0
    avg_comfort_rate = DailyComfortStat.objects.aggregate(
        avg=models.Avg("comfort_rate")
    )["avg"] or 100

    health_score = max(
        0,
        round(100 - float(avg_risk_rate) * 0.55 - (100 - float(avg_comfort_rate)) * 0.25),
    )

    if health_score >= 85:
        level, level_text = "good", "气象环境优良"
        advice = "当前气象环境优良，各项指标正常，可按常规管理方案运行"
    elif health_score >= 70:
        level, level_text = "normal", "气象环境一般"
        advice = "建议保持常规巡查，关注气象指标变化"
    elif health_score >= 50:
        level, level_text = "warning", "气象环境偏差"
        advice = "建议加强监测频率，关注高温、高湿及PM2.5指标"
    else:
        level, level_text = "danger", "气象环境恶劣"
        advice = "建议启动应急预案，加强防火及空气质量管控措施"

    return {
        "level": level,
        "level_text": level_text,
        "health_score": health_score,
        "average_risk_rate": round(float(avg_risk_rate), 2),
        "average_comfort_rate": round(float(avg_comfort_rate), 2),
        "advice": advice,
    }


# =====================
# 8. Pipeline
# =====================
def run_weather_full_pipeline():
    """执行完整的气象数据分析流水线"""
    print("===== START WEATHER PIPELINE =====")

    jobs = [
        ("upload", "上传CSV到HDFS", upload_csv_to_hdfs),
        ("stats", "每日气象统计MR", run_mr_weather_stats),
        ("hourly", "小时气象分布MR", run_mr_hourly_profile),
        ("comfort", "舒适度统计MR", run_mr_daily_comfort),
        ("risk", "风险统计MR", run_mr_daily_risk),
        ("topn", "风险TopN排名MR", run_mr_risk_topn),
    ]

    steps = []
    all_success = True

    for job_key, job_name, run_func in jobs:
        step = {"step": job_key, "name": job_name, "success": False}
        try:
            step.update({"success": True, "detail": run_func()})
        except Exception as exc:
            step["error"] = str(exc)
            all_success = False
        steps.append(step)

        if not all_success and job_key != "upload":
            break

    if not all_success:
        MapReduceSyncLog.objects.create(status="failed", message="MR执行失败")
        return {"status": "error", "steps": steps}

    print("===== MR DONE =====")

    imports = [
        ("load_stats", "导入气象统计数据", load_weather_stats_to_mysql),
        ("load_hourly", "导入小时分布数据", load_hourly_profile_to_mysql),
        ("load_comfort", "导入舒适度数据", load_comfort_to_mysql),
        ("load_risk", "导入风险统计数据", load_risk_to_mysql),
        ("load_topn", "导入风险TopN数据", load_topn_to_mysql),
    ]

    for job_key, job_name, import_func in imports:
        step = {"step": job_key, "name": job_name, "success": False}
        try:
            imported_rows = import_func()
            step.update({"success": True, "imported_rows": imported_rows})
        except Exception as exc:
            step["error"] = str(exc)
            all_success = False
        steps.append(step)

        if not all_success:
            break

    print("===== MYSQL DONE =====")

    if all_success:
        MapReduceSyncLog.objects.create(status="success", message="气象数据同步完成")
    else:
        MapReduceSyncLog.objects.create(status="failed", message="部分数据导入失败")

    report = get_weather_health_summary()
    return {"status": "ok" if all_success else "error", "steps": steps, "report": report}
