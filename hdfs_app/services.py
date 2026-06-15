import os
import shlex
from pathlib import Path

import paramiko
from django.conf import settings


SSH_HOST = "192.168.56.100"
SSH_PORT = 22
SSH_USERNAME = "root"

# 可临时把 root 密码写在第二个参数中，例如：os.getenv("HADOOP_SSH_PASSWORD", "123456")。
# 当前优先使用启动 Django 前设置的 HADOOP_SSH_PASSWORD 环境变量。
SSH_PASSWORD = os.getenv("HADOOP_SSH_PASSWORD", "")
SSH_KEY_FILENAME = os.getenv("HADOOP_SSH_KEY_FILENAME", "")

LOCAL_CSV_PATH = Path(settings.BASE_DIR) / "datasets" / "visitor_records.csv"
REMOTE_CSV_PATH = "/root/forest_monitor/datasets/visitor_records.csv"
REMOTE_DATASET_DIR = "/root/forest_monitor/datasets"
HDFS_DIRECTORY = "/forest/visitor/input"
HDFS_FILE_PATH = "/forest/visitor/input/visitor_records.csv"


def _create_ssh_client():
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    options = {
        "hostname": SSH_HOST,
        "port": SSH_PORT,
        "username": SSH_USERNAME,
        "timeout": 15,
        "banner_timeout": 15,
        "auth_timeout": 15,
    }
    if SSH_PASSWORD:
        options["password"] = SSH_PASSWORD
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


def hdfs_list():
    return _run_hadoop_command(f"hdfs dfs -ls -h {HDFS_DIRECTORY}")


def hdfs_preview():
    result = _run_hadoop_command(f"hdfs dfs -cat {HDFS_FILE_PATH} | head -20")
    if "Unable to write to output stream" in result["stderr"]:
        result["stderr"] = result["stderr"].replace(
            "cat: Unable to write to output stream.", ""
        ).strip()
        if result["stdout"]:
            result["success"] = True
            result["returncode"] = 0
    return result


def hdfs_upload():
    if not LOCAL_CSV_PATH.exists():
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Windows 本地文件不存在：{LOCAL_CSV_PATH}",
            "returncode": -1,
        }

    prepare_result = run_ssh_command(
        f"mkdir -p {shlex.quote(REMOTE_DATASET_DIR)}"
    )
    if not prepare_result["success"]:
        return prepare_result

    try:
        client = _create_ssh_client()
        try:
            with client.open_sftp() as sftp:
                sftp.put(str(LOCAL_CSV_PATH), REMOTE_CSV_PATH)
        finally:
            client.close()
    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"SFTP 上传失败：{exc}",
            "returncode": -1,
        }

    command = " && ".join(
        [
            f"hdfs dfs -mkdir -p {HDFS_DIRECTORY}",
            f"hdfs dfs -put -f {REMOTE_CSV_PATH} {HDFS_DIRECTORY}/",
            f"hdfs dfs -test -e {HDFS_FILE_PATH}",
        ]
    )
    result = _run_hadoop_command(command)
    if result["success"]:
        result["stdout"] = (
            f"上传成功：{LOCAL_CSV_PATH}\n"
            f"Linux 文件：{REMOTE_CSV_PATH}\n"
            f"HDFS 文件：{HDFS_FILE_PATH}"
        )
    return result


def hdfs_delete():
    return _run_hadoop_command(f"hdfs dfs -rm -f {HDFS_FILE_PATH}")
