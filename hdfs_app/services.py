import os
import shlex
from datetime import datetime
from pathlib import Path

import paramiko
from django.conf import settings

SSH_HOST = os.getenv("HADOOP_SSH_HOST", "192.168.56.100")
SSH_PORT = int(os.getenv("HADOOP_SSH_PORT", "22"))
SSH_USERNAME = os.getenv("HADOOP_SSH_USERNAME", "root")

# 可临时把 root 密码写在第二个参数中，例如：os.getenv("HADOOP_SSH_PASSWORD", "123456")。
SSH_PASSWORD = os.getenv("HADOOP_SSH_PASSWORD", "")
SSH_KEY_FILENAME = os.getenv("HADOOP_SSH_KEY_FILENAME", "")

REMOTE_DATASET_DIR = os.getenv(
    "HADOOP_REMOTE_DATASET_DIR", "/root/forest_monitor/datasets"
)
HDFS_BASE_DIR = os.getenv("HDFS_BASE_DIR", "/forest")

# 设备数据 HDFS 路径
HDFS_DEVICES_INPUT_DIR = os.getenv(
    "HDFS_DEVICES_INPUT_DIR", f"{HDFS_BASE_DIR}/device/input"
)
HDFS_DEVICES_OUTPUT_DIR = os.getenv(
    "HDFS_DEVICES_OUTPUT_DIR", f"{HDFS_BASE_DIR}/device/output"
)
HDFS_DEVICES_FAULT_OUTPUT_DIR = f"{HDFS_DEVICES_OUTPUT_DIR}/fault"
HDFS_DEVICES_HEALTH_OUTPUT_DIR = f"{HDFS_DEVICES_OUTPUT_DIR}/health"
HDFS_DEVICES_LOCATION_OUTPUT_DIR = f"{HDFS_DEVICES_OUTPUT_DIR}/location"
HDFS_DEVICES_ANALYSIS_OUTPUT_DIR = f"{HDFS_DEVICES_OUTPUT_DIR}/analysis"

# 游客数据 HDFS 路径
HDFS_VISITORS_INPUT_DIR = os.getenv(
    "HDFS_VISITORS_INPUT_DIR", "/forest/visitor/input"
)
HDFS_VISITORS_OUTPUT_DIR = os.getenv(
    "HDFS_VISITORS_OUTPUT_DIR", "/forest/visitor/output"
)
HDFS_VISITORS_DAILY_OUTPUT_DIR = f"{HDFS_VISITORS_OUTPUT_DIR}/daily"
HDFS_VISITORS_GATE_OUTPUT_DIR = f"{HDFS_VISITORS_OUTPUT_DIR}/gate"
HDFS_VISITORS_HOURLY_OUTPUT_DIR = f"{HDFS_VISITORS_OUTPUT_DIR}/hourly"

# 游客数据历史文件路径
HDFS_VISITORS_HISTORY_DIR = f"{HDFS_VISITORS_INPUT_DIR}/history"
HDFS_VISITORS_HISTORY_FILE = f"{HDFS_VISITORS_HISTORY_DIR}/visitor_records.csv"
HDFS_VISITORS_LEGACY_FILE = f"{HDFS_VISITORS_INPUT_DIR}/visitor_records.csv"
LOCAL_HISTORY_FILE = Path(settings.BASE_DIR) / "datasets" / "visitor_records.csv"
REMOTE_HISTORY_FILE = "/root/forest_monitor/datasets/visitor_records.csv"
VISITOR_HISTORY_FILES = {
    "visitor_records.csv": LOCAL_HISTORY_FILE,
}
VISITOR_DATASET_FILES = {
    "visitor_records.csv": LOCAL_HISTORY_FILE,
    "visitor_today.csv": Path(settings.BASE_DIR) / "datasets" / "visitor_today.csv",
}


def get_visitor_dataset_files():
    dataset_dir = Path(settings.BASE_DIR) / "datasets"
    files = {
        "visitor_records.csv": LOCAL_HISTORY_FILE,
    }
    today_file = dataset_dir / "visitor_today.csv"
    if today_file.is_file():
        files[today_file.name] = today_file
    for path in sorted(dataset_dir.glob("visitor_records_*.csv")):
        if path.is_file():
            files[path.name] = path
    return files
DEVICE_DATASET_FILES = {
    "devices_info.csv": Path(settings.BASE_DIR) / "datasets" / "devices_info.csv",
    "devices_work_log.csv": Path(settings.BASE_DIR) / "datasets" / "devices_work_log.csv",
    "devices_fault_log.csv": Path(settings.BASE_DIR) / "datasets" / "devices_fault_log.csv",
}
HDFS_WEATHER_INPUT_DIR = os.getenv(
    "HDFS_WEATHER_INPUT_DIR", f"{HDFS_BASE_DIR}/weather/input"
)
WEATHER_DATASET_FILES = {
    "weather_15days.csv": Path(settings.BASE_DIR) / "datasets" / "weather_15days.csv",
    "weather_7days.csv": Path(settings.BASE_DIR) / "datasets" / "weather_7days.csv",
}


def validate_date_str(date_str):
    """校验日期格式，避免日期参数进入命令时产生注入风险。"""
    try:
        parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise ValueError("日期必须使用 YYYY-MM-DD 格式。") from exc
    if parsed_date.strftime("%Y-%m-%d") != date_str:
        raise ValueError("日期必须使用 YYYY-MM-DD 格式。")
    return date_str


def get_hdfs_date_dir(date_str):
    validate_date_str(date_str)
    return f"{HDFS_VISITORS_INPUT_DIR}/date={date_str}"


def _create_ssh_client():
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    options = {
        "hostname": SSH_HOST,
        "port": SSH_PORT,
        "username": SSH_USERNAME,
        "timeout": 20,
        "banner_timeout": 20,
        "auth_timeout": 30,
    }
    if SSH_PASSWORD:
        options["password"] = SSH_PASSWORD
        options["allow_agent"] = False
        options["look_for_keys"] = False
    if SSH_KEY_FILENAME:
        options["key_filename"] = SSH_KEY_FILENAME

    client.connect(**options)
    return client


def run_ssh_command(command):
    """在 hd0 执行固定 Linux 命令并返回统一结果。"""
    try:
        client = _create_ssh_client()
        try:
            stdin, stdout, stderr = client.exec_command(command, get_pty=True)
            del stdin
            stdout_text = stdout.read().decode("utf-8", errors="replace").strip()
            stderr_text = stderr.read().decode("utf-8", errors="replace").strip()
            returncode = stdout.channel.recv_exit_status()
            return {
                "success": returncode == 0,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "returncode": returncode,
            }
        finally:
            client.close()
    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
            "returncode": -1,
        }


def _run_hadoop_command(command):
    return run_ssh_command(f"bash -lc {shlex.quote(command)}")


def _ignore_broken_pipe(result):
    if "Unable to write to output stream" in result["stderr"]:
        result["stderr"] = result["stderr"].replace(
            "cat: Unable to write to output stream.", ""
        ).strip()
        if result["stdout"]:
            result["success"] = True
            result["returncode"] = 0
    return result


def hdfs_list():
    return _run_hadoop_command(
        f"hdfs dfs -ls -R -h {shlex.quote(HDFS_VISITORS_INPUT_DIR)}"
    )


def _sftp_upload(local_path, remote_path):
    try:
        client = _create_ssh_client()
        try:
            with client.open_sftp() as sftp:
                sftp.put(str(local_path), remote_path)
        finally:
            client.close()
    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"SFTP 上传失败：{exc}",
            "returncode": -1,
        }
    return None


def hdfs_upload_history():
    if not LOCAL_HISTORY_FILE.is_file():
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Windows 历史数据文件不存在：{LOCAL_HISTORY_FILE}",
            "returncode": -1,
        }

    prepare_result = run_ssh_command(
        f"mkdir -p {shlex.quote(REMOTE_DATASET_DIR)}"
    )
    if not prepare_result["success"]:
        return prepare_result

    upload_error = _sftp_upload(LOCAL_HISTORY_FILE, REMOTE_HISTORY_FILE)
    if upload_error:
        return upload_error

    command = " && ".join(
        [
            f"hdfs dfs -mkdir -p {shlex.quote(HDFS_VISITORS_HISTORY_DIR)}",
            (
                f"hdfs dfs -put -f {shlex.quote(REMOTE_HISTORY_FILE)} "
                f"{shlex.quote(HDFS_VISITORS_HISTORY_FILE)}"
            ),
            f"hdfs dfs -test -e {shlex.quote(HDFS_VISITORS_HISTORY_FILE)}",
            f"hdfs dfs -rm -f {shlex.quote(HDFS_VISITORS_LEGACY_FILE)}",
            f"hdfs dfs -ls -h {shlex.quote(HDFS_VISITORS_HISTORY_FILE)}",
        ]
    )
    result = _run_hadoop_command(command)
    if result["success"]:
        detail = result["stdout"]
        result["stdout"] = (
            f"Windows 文件：{LOCAL_HISTORY_FILE}\n"
            f"Linux 文件：{REMOTE_HISTORY_FILE}\n"
            f"HDFS 文件：{HDFS_VISITORS_HISTORY_FILE}\n"
            f"校验结果：{detail}"
        )
    return result


def hdfs_upload_by_date(local_csv_path, date_str):
    date_str = validate_date_str(date_str)
    local_csv_path = Path(local_csv_path)
    if not local_csv_path.is_file():
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Windows 本地文件不存在：{local_csv_path}",
            "returncode": -1,
        }

    remote_csv_path = (
        f"{REMOTE_DATASET_DIR}/visitor_records_{date_str}.csv"
    )
    hdfs_date_dir = get_hdfs_date_dir(date_str)
    hdfs_file_path = f"{hdfs_date_dir}/visitor_records.csv"

    prepare_result = run_ssh_command(
        f"mkdir -p {shlex.quote(REMOTE_DATASET_DIR)}"
    )
    if not prepare_result["success"]:
        return prepare_result

    upload_error = _sftp_upload(local_csv_path, remote_csv_path)
    if upload_error:
        return upload_error

    command = " && ".join(
        [
            f"hdfs dfs -mkdir -p {shlex.quote(hdfs_date_dir)}",
            (
                f"hdfs dfs -put -f {shlex.quote(remote_csv_path)} "
                f"{shlex.quote(hdfs_file_path)}"
            ),
            f"hdfs dfs -test -e {shlex.quote(hdfs_file_path)}",
            f"hdfs dfs -ls -h {shlex.quote(hdfs_file_path)}",
        ]
    )
    result = _run_hadoop_command(command)
    if result["success"]:
        detail = result["stdout"]
        result["stdout"] = (
            f"Windows 文件：{local_csv_path}\n"
            f"Linux 文件：{remote_csv_path}\n"
            f"HDFS 文件：{hdfs_file_path}\n"
            f"校验结果：{detail}"
        )
    return result


def hdfs_preview_history():
    result = _run_hadoop_command(
        f"hdfs dfs -cat {shlex.quote(HDFS_VISITORS_HISTORY_FILE)} | head -20"
    )
    return _ignore_broken_pipe(result)


def hdfs_delete_history():
    return _run_hadoop_command(
        f"hdfs dfs -rm -f {shlex.quote(HDFS_VISITORS_HISTORY_FILE)}"
    )


def _visitor_hdfs_file_path(filename):
    if filename == "visitor_records.csv":
        return HDFS_VISITORS_HISTORY_FILE
    return f"{HDFS_VISITORS_INPUT_DIR}/{filename}"


def hdfs_upload_visitor_file(local_csv_path, filename):
    local_csv_path = Path(local_csv_path)
    if filename not in get_visitor_dataset_files():
        return {
            "success": False,
            "stdout": "",
            "stderr": "不支持的游客数据文件。",
            "returncode": -1,
        }
    if not local_csv_path.is_file():
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Windows 本地文件不存在：{local_csv_path}",
            "returncode": -1,
        }

    prepare_result = run_ssh_command(
        f"mkdir -p {shlex.quote(REMOTE_DATASET_DIR)}"
    )
    if not prepare_result["success"]:
        return prepare_result

    remote_csv_path = f"{REMOTE_DATASET_DIR}/{filename}"
    upload_error = _sftp_upload(local_csv_path, remote_csv_path)
    if upload_error:
        return upload_error

    hdfs_file_path = _visitor_hdfs_file_path(filename)
    hdfs_parent = str(Path(hdfs_file_path).parent).replace("\\", "/")
    command = " && ".join(
        [
            f"hdfs dfs -mkdir -p {shlex.quote(hdfs_parent)}",
            (
                f"hdfs dfs -put -f {shlex.quote(remote_csv_path)} "
                f"{shlex.quote(hdfs_file_path)}"
            ),
            f"hdfs dfs -test -e {shlex.quote(hdfs_file_path)}",
            f"hdfs dfs -ls -h {shlex.quote(hdfs_file_path)}",
        ]
    )
    result = _run_hadoop_command(command)
    if result["success"]:
        detail = result["stdout"]
        result["stdout"] = (
            f"Windows 文件：{local_csv_path}\n"
            f"Linux 临时文件：{remote_csv_path}\n"
            f"HDFS 文件：{hdfs_file_path}\n"
            f"校验结果：{detail}"
        )
    return result


def hdfs_preview_visitor_file(filename):
    if filename not in get_visitor_dataset_files():
        return {
            "success": False,
            "stdout": "",
            "stderr": "不支持的游客数据文件。",
            "returncode": -1,
        }
    hdfs_file_path = _visitor_hdfs_file_path(filename)
    result = _run_hadoop_command(
        f"hdfs dfs -cat {shlex.quote(hdfs_file_path)} | head -20"
    )
    return _ignore_broken_pipe(result)


def hdfs_delete_visitor_file(filename):
    if filename not in get_visitor_dataset_files():
        return {
            "success": False,
            "stdout": "",
            "stderr": "不支持的游客数据文件。",
            "returncode": -1,
        }
    return _run_hadoop_command(
        f"hdfs dfs -rm -f {shlex.quote(_visitor_hdfs_file_path(filename))}"
    )


def hdfs_preview_by_date(date_str):
    hdfs_file_path = f"{get_hdfs_date_dir(date_str)}/visitor_records.csv"
    result = _run_hadoop_command(
        f"hdfs dfs -cat {shlex.quote(hdfs_file_path)} | head -20"
    )
    return _ignore_broken_pipe(result)


def hdfs_preview_tail_by_date(date_str):
    hdfs_file_path = f"{get_hdfs_date_dir(date_str)}/visitor_records.csv"
    result = _run_hadoop_command(
        f"hdfs dfs -cat {shlex.quote(hdfs_file_path)} | tail -20"
    )
    return _ignore_broken_pipe(result)


def hdfs_delete_by_date(date_str):
    hdfs_date_dir = get_hdfs_date_dir(date_str)
    return _run_hadoop_command(
        f"hdfs dfs -rm -r -f {shlex.quote(hdfs_date_dir)}"
    )

# ================= 设备模块 (Devices) 管理方法 =================

def hdfs_devices_list():
    """列出设备模块下的所有文件"""
    return _run_hadoop_command(
        f"hdfs dfs -ls -R -h {shlex.quote(HDFS_DEVICES_INPUT_DIR)}"
    )

def hdfs_upload_devices(local_csv_path, filename):
    """
    上传设备数据文件到 HDFS input 目录
    :param local_csv_path: 本地文件绝对路径
    :param filename: 目标文件名，如 devices_info.csv, devices_work_log.csv
    """
    local_csv_path = Path(local_csv_path)
    if not local_csv_path.is_file():
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Windows 本地文件不存在：{local_csv_path}",
            "returncode": -1,
        }

    # 在远程 Linux 准备临时目录
    prepare_result = run_ssh_command(
        f"mkdir -p {shlex.quote(REMOTE_DATASET_DIR)}"
    )
    if not prepare_result["success"]:
        return prepare_result

    remote_csv_path = f"{REMOTE_DATASET_DIR}/{filename}"
    upload_error = _sftp_upload(local_csv_path, remote_csv_path)
    if upload_error:
        return upload_error

    # 创建 HDFS 目录并上传
    command = " && ".join(
        [
            f"hdfs dfs -mkdir -p {shlex.quote(HDFS_DEVICES_INPUT_DIR)}",
            (
                f"hdfs dfs -put -f {shlex.quote(remote_csv_path)} "
                f"{shlex.quote(HDFS_DEVICES_INPUT_DIR)}/{shlex.quote(filename)}"
            ),
            f"hdfs dfs -test -e {shlex.quote(HDFS_DEVICES_INPUT_DIR)}/{shlex.quote(filename)}",
            f"hdfs dfs -ls -h {shlex.quote(HDFS_DEVICES_INPUT_DIR)}/{shlex.quote(filename)}",
        ]
    )
    result = _run_hadoop_command(command)
    if result["success"]:
        detail = result["stdout"]
        result["stdout"] = (
            f"Windows 文件：{local_csv_path}\n"
            f"Linux 临时文件：{remote_csv_path}\n"
            f"HDFS 文件：{HDFS_DEVICES_INPUT_DIR}/{filename}\n"
            f"校验结果：{detail}"
        )
    return result

def hdfs_preview_devices(filename):
    """预览设备数据文件的前20行"""
    hdfs_file_path = f"{HDFS_DEVICES_INPUT_DIR}/{filename}"
    result = _run_hadoop_command(
        f"hdfs dfs -cat {shlex.quote(hdfs_file_path)} | head -20"
    )
    return _ignore_broken_pipe(result)

def hdfs_delete_devices(filename):
    """删除指定的设备数据文件"""
    hdfs_file_path = f"{HDFS_DEVICES_INPUT_DIR}/{filename}"
    return _run_hadoop_command(
        f"hdfs dfs -rm -f {shlex.quote(hdfs_file_path)}"
    )


# ================= 气象模块 HDFS 管理方法 =================

def hdfs_weather_list():
    return _run_hadoop_command(
        f"hdfs dfs -ls -R -h {shlex.quote(HDFS_WEATHER_INPUT_DIR)}"
    )


def hdfs_upload_weather(local_csv_path, filename):
    local_csv_path = Path(local_csv_path)
    if filename not in WEATHER_DATASET_FILES:
        return {
            "success": False,
            "stdout": "",
            "stderr": "不支持的气象数据文件。",
            "returncode": -1,
        }
    if not local_csv_path.is_file():
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Windows 本地文件不存在：{local_csv_path}",
            "returncode": -1,
        }

    prepare_result = run_ssh_command(
        f"mkdir -p {shlex.quote(REMOTE_DATASET_DIR)}"
    )
    if not prepare_result["success"]:
        return prepare_result

    remote_csv_path = f"{REMOTE_DATASET_DIR}/{filename}"
    upload_error = _sftp_upload(local_csv_path, remote_csv_path)
    if upload_error:
        return upload_error

    hdfs_file_path = f"{HDFS_WEATHER_INPUT_DIR}/{filename}"
    command = " && ".join(
        [
            f"hdfs dfs -mkdir -p {shlex.quote(HDFS_WEATHER_INPUT_DIR)}",
            (
                f"hdfs dfs -put -f {shlex.quote(remote_csv_path)} "
                f"{shlex.quote(hdfs_file_path)}"
            ),
            f"hdfs dfs -test -e {shlex.quote(hdfs_file_path)}",
            f"hdfs dfs -ls -h {shlex.quote(hdfs_file_path)}",
        ]
    )
    result = _run_hadoop_command(command)
    if result["success"]:
        detail = result["stdout"]
        result["stdout"] = (
            f"Windows 文件：{local_csv_path}\n"
            f"Linux 临时文件：{remote_csv_path}\n"
            f"HDFS 文件：{hdfs_file_path}\n"
            f"校验结果：{detail}"
        )
    return result


def hdfs_preview_weather(filename):
    if filename not in WEATHER_DATASET_FILES:
        return {
            "success": False,
            "stdout": "",
            "stderr": "不支持的气象数据文件。",
            "returncode": -1,
        }
    hdfs_file_path = f"{HDFS_WEATHER_INPUT_DIR}/{filename}"
    result = _run_hadoop_command(
        f"hdfs dfs -cat {shlex.quote(hdfs_file_path)} | head -20"
    )
    return _ignore_broken_pipe(result)


def hdfs_delete_weather(filename):
    if filename not in WEATHER_DATASET_FILES:
        return {
            "success": False,
            "stdout": "",
            "stderr": "不支持的气象数据文件。",
            "returncode": -1,
        }
    hdfs_file_path = f"{HDFS_WEATHER_INPUT_DIR}/{filename}"
    return _run_hadoop_command(
        f"hdfs dfs -rm -f {shlex.quote(hdfs_file_path)}"
    )
