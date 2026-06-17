from django.shortcuts import render

from .services import hdfs_delete, hdfs_list, hdfs_preview, hdfs_upload


def _result_message(action_name, result):
    if result["success"]:
        detail = result["stdout"] or "命令执行成功"
        return f"{action_name}成功。\n{detail}", "success"
    detail = result["stderr"] or result["stdout"] or "未知错误"
    return f"{action_name}失败。\n{detail}", "error"


def hdfs_index(request):
    message = ""
    message_type = ""
    preview_text = ""

    if request.method == "POST":
        action = request.POST.get("action", "")
        action_config = {
            "list": ("查看文件列表", hdfs_list),
            "upload": ("上传/覆盖文件", hdfs_upload),
            "preview": ("预览文件", hdfs_preview),
            "delete": ("删除文件", hdfs_delete),
        }.get(action)
        if action_config is None:
            message = "不支持的操作。"
            message_type = "error"
        else:
            action_name, action_function = action_config
            result = action_function()
            message, message_type = _result_message(action_name, result)
            if action == "preview" and result["success"]:
                preview_text = result["stdout"]

    list_result = hdfs_list()
    file_list = list_result["stdout"] if list_result["success"] else ""
    if not message and not list_result["success"]:
        message, message_type = _result_message("读取 HDFS 文件列表", list_result)

    return render(
        request,
        "hdfs/index.html",
        {
            "message": message,
            "message_type": message_type,
            "file_list": file_list,
            "preview_text": preview_text,
            "hdfs_directory": "/forest/visitor/input",
            "hdfs_file_path": "/forest/visitor/input/visitor_records.csv",
        },
    )
