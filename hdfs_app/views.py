from datetime import datetime, time, timedelta
from pathlib import Path

from django.conf import settings
from django.shortcuts import render
from django.utils import timezone
from visitor.models import VisitorRecord

from .services import (
    HDFS_BASE_DIR,
    HDFS_VISITORS_HISTORY_FILE,
    hdfs_delete_by_date,
    hdfs_list,
    hdfs_preview_by_date,
    hdfs_preview_history,
    hdfs_preview_tail_by_date,
    hdfs_upload_by_date,
    hdfs_upload_history,
    validate_date_str,
)


UPLOAD_DIR = Path(settings.BASE_DIR) / "datasets" / "upload_date"


def _result_message(action_name, result):
    if result["success"]:
        detail = result["stdout"] or "命令执行成功"
        return f"{action_name}成功。\n{detail}", "success"
    detail = result["stderr"] or result["stdout"] or "未知错误"
    return f"{action_name}失败。\n{detail}", "error"


def _save_uploaded_csv(uploaded_file, date_str):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    local_path = UPLOAD_DIR / f"visitor_records_{date_str}.csv"
    with local_path.open("wb") as target:
        for chunk in uploaded_file.chunks():
            target.write(chunk)
    return local_path


def hdfs_index(request):
    message = ""
    message_type = ""
    preview_text = ""
    selected_date = ""

    if request.method == "POST":
        action = request.POST.get("action", "")
        # 某些浏览器在提交按钮进入 disabled 状态后不会提交按钮的 name/value。
        # 根据固定表单字段兜底识别操作，不接受用户自定义命令或路径。
        if not action:
            if "csv_file" in request.FILES and "date_str" in request.POST:
                action = "upload_by_date"
            elif "delete_date" in request.POST:
                action = "delete_by_date"
        try:
            if action == "upload_history":
                result = hdfs_upload_history()
                if result["success"]:
                    message = "历史游客数据已上传到 HDFS history 目录。"
                    message_type = "success"
                else:
                    message, message_type = _result_message("上传历史游客数据", result)

            elif action == "preview_history":
                result = hdfs_preview_history()
                if result["success"]:
                    preview_text = result["stdout"]
                    message = "历史数据前 20 行加载成功，请在下方预览区域查看。"
                    message_type = "success"
                else:
                    message, message_type = _result_message(
                        "预览历史数据前 20 行", result
                    )

            elif action == "upload_by_date":
                selected_date = validate_date_str(request.POST.get("date_str", ""))
                uploaded_file = request.FILES.get("csv_file")
                if uploaded_file is None:
                    raise ValueError("请选择需要上传的 CSV 文件。")
                if Path(uploaded_file.name).suffix.lower() != ".csv":
                    raise ValueError("只能上传 .csv 文件。")

                local_path = _save_uploaded_csv(uploaded_file, selected_date)
                result = hdfs_upload_by_date(local_path, selected_date)
                if result["success"]:
                    message = (
                        f"已上传 {selected_date} 游客数据到 HDFS 日期分区，"
                    )
                    message_type = "success"
                else:
                    message, message_type = _result_message("上传日期分区", result)

            elif action in {"preview_by_date", "preview_tail_by_date"}:
                selected_date = validate_date_str(
                    request.POST.get("preview_date", "")
                )
                if action == "preview_by_date":
                    result = hdfs_preview_by_date(selected_date)
                    action_name = "预览前 20 行"
                else:
                    result = hdfs_preview_tail_by_date(selected_date)
                    action_name = "预览最后 20 行"
                if result["success"]:
                    preview_text = result["stdout"]
                    message = f"{selected_date} 数据{action_name}加载成功，请在下方预览区域查看。"
                    message_type = "success"
                else:
                    message, message_type = _result_message(action_name, result)

            elif action == "delete_by_date":
                selected_date = validate_date_str(
                    request.POST.get("delete_date", "")
                )
                result = hdfs_delete_by_date(selected_date)
                if result["success"]:
                    target_date = datetime.strptime(
                        selected_date, "%Y-%m-%d"
                    ).date()
                    day_start = timezone.make_aware(
                        datetime.combine(target_date, time.min)
                    )
                    day_end = day_start + timedelta(days=1)
                    records = VisitorRecord.objects.filter(
                        visit_time__gte=day_start,
                        visit_time__lt=day_end,
                    )
                    deleted_rows = records.count()
                    records.delete()
                    local_path = (
                        UPLOAD_DIR / f"visitor_records_{selected_date}.csv"
                    )
                    if local_path.exists():
                        local_path.unlink()
                    message = (
                        f"已删除 {selected_date} HDFS 日期分区，"
                        f"并同步删除 MySQL 中 {deleted_rows} 条游客记录。"
                    )
                    message_type = "success"
                else:
                    message, message_type = _result_message(
                        f"删除 {selected_date} 日期分区", result
                    )

            elif action == "list":
                pass
            else:
                message = "不支持的操作。"
                message_type = "error"
        except (OSError, ValueError) as exc:
            message = str(exc)
            message_type = "error"

    # 分区目录可能被其他 Hadoop 任务修改，因此每次打开页面都读取完整目录。
    list_result = hdfs_list()
    file_list = list_result["stdout"] if list_result["success"] else ""
    if not list_result["success"] and not message:
        message, message_type = _result_message("读取 HDFS 日期分区列表", list_result)

    return render(
        request,
        "hdfs/index.html",
        {
            "page": "hdfs",
            "message": message,
            "message_type": message_type,
            "file_list": file_list,
            "preview_text": preview_text,
            "selected_date": selected_date,
            "hdfs_directory": HDFS_BASE_DIR,
            "hdfs_history_file": HDFS_VISITORS_HISTORY_FILE,
        },
    )
