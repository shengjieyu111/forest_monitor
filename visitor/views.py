from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum
from django.db.models.functions import ExtractHour, TruncDate
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import VisitorRecordForm
from .models import (
    VisitorDailyStat,
    VisitorGateStat,
    VisitorHourlyStat,
    VisitorRecord,
)
from .services import (
    get_peak_warning,
    import_daily_result,
    import_gate_result,
    import_hourly_result,
    import_visitor_records_from_csv,
    run_daily_mapreduce_remote,
    run_gate_mapreduce_remote,
    run_hourly_mapreduce_remote,
    upload_visitor_csv_to_hdfs_remote,
)


def _date_range(days):
    end = timezone.localdate()
    start = end - timedelta(days=days - 1)
    return start, end


def _scale_rows(rows, value_key):
    peak_value = max([row[value_key] for row in rows], default=0) or 1
    for row in rows:
        row["percent"] = round(row[value_key] / peak_value * 100, 1)
    return rows


def dashboard(request):
    days = int(request.GET.get("days", 7))
    days = min(max(days, 1), 30)
    start, end = _date_range(days)

    if request.method == "POST":
        form = VisitorRecordForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "游客记录已保存。")
            return redirect("visitor:dashboard")
    else:
        form = VisitorRecordForm()

    records = VisitorRecord.objects.filter(visit_time__date__range=(start, end))
    total_visitors = records.aggregate(total=Sum("visitor_count"))["total"] or 0
    total_records = records.count()
    average_daily = round(total_visitors / days, 1) if days else 0

    trend_rows = list(
        records.annotate(day=TruncDate("visit_time"))
        .values("day")
        .annotate(total=Sum("visitor_count"))
        .order_by("day")
    )
    trend_rows = [
        {"label": row["day"].strftime("%m-%d"), "total": row["total"] or 0}
        for row in trend_rows
    ]
    trend_rows = _scale_rows(trend_rows, "total")

    hourly_rows = list(
        records.annotate(hour=ExtractHour("visit_time"))
        .values("hour")
        .annotate(total=Sum("visitor_count"))
        .order_by("hour")
    )
    hourly_rows = [
        {"label": f"{row['hour']:02d}:00", "total": row["total"] or 0}
        for row in hourly_rows
    ]
    hourly_rows = _scale_rows(hourly_rows, "total")
    peak_hour = max(hourly_rows, key=lambda row: row["total"], default=None)

    entrance_rows = list(
        records.values("gate")
        .annotate(total=Sum("visitor_count"))
        .order_by("-total")
    )
    entrance_rows = [
        {
            "label": row["gate"],
            "total": row["total"] or 0,
        }
        for row in entrance_rows
    ]
    entrance_rows = _scale_rows(entrance_rows, "total")

    recent_records = VisitorRecord.objects.all()[:12]

    context = {
        "days": days,
        "start": start,
        "end": end,
        "form": form,
        "total_visitors": total_visitors,
        "total_records": total_records,
        "average_daily": average_daily,
        "trend_rows": trend_rows,
        "hourly_rows": hourly_rows,
        "peak_hour": peak_hour,
        "entrance_rows": entrance_rows,
        "recent_records": recent_records,
        "mr_hourly_stats": VisitorHourlyStat.objects.all(),
        "mr_gate_stats": VisitorGateStat.objects.all(),
    }
    return render(request, "visitor/dashboard.html", context)


def api_response(data, message="success"):
    return JsonResponse(
        {"code": 0, "message": message, "data": data},
        json_dumps_params={"ensure_ascii": False},
    )


def visitor_record_list_api(request):
    try:
        page_number = max(int(request.GET.get("page", 1)), 1)
        page_size = min(max(int(request.GET.get("page_size", 20)), 1), 200)
    except ValueError:
        return JsonResponse(
            {"code": 400, "message": "page 和 page_size 必须是整数", "data": None},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    records = VisitorRecord.objects.all()
    gate = request.GET.get("gate", "").strip()
    ticket_type = request.GET.get("ticket_type", "").strip()
    if gate:
        records = records.filter(gate=gate)
    if ticket_type:
        records = records.filter(ticket_type=ticket_type)

    paginator = Paginator(records, page_size)
    page = paginator.get_page(page_number)
    items = [
        {
            "id": record.id,
            "visit_time": timezone.localtime(record.visit_time).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "gate": record.gate,
            "visitor_count": record.visitor_count,
            "weather": record.weather,
            "ticket_type": record.ticket_type,
        }
        for record in page.object_list
    ]
    return api_response(
        {
            "items": items,
            "page": page.number,
            "page_size": page_size,
            "total": paginator.count,
            "total_pages": paginator.num_pages,
        }
    )


def visitor_daily_stat_api(request):
    rows = list(VisitorDailyStat.objects.order_by("stat_date"))
    return api_response(
        {
            "labels": [row.stat_date.strftime("%Y-%m-%d") for row in rows],
            "values": [row.total_count for row in rows],
        }
    )


def visitor_hourly_stat_api(request):
    rows = list(VisitorHourlyStat.objects.order_by("hour"))
    peak = max(rows, key=lambda row: row.total_count, default=None)
    return api_response(
        {
            "labels": [f"{row.hour:02d}:00" for row in rows],
            "values": [row.total_count for row in rows],
            "peak": (
                {"hour": f"{peak.hour:02d}:00", "total_count": peak.total_count}
                if peak
                else None
            ),
        }
    )


def visitor_gate_stat_api(request):
    rows = VisitorGateStat.objects.order_by("gate")
    return api_response(
        [
            {"name": row.gate, "value": row.total_count}
            for row in rows
        ]
    )


def peak_warning_api(request):
    return api_response(get_peak_warning())


@require_POST
def run_all_mr_and_import_api(request):
    jobs = [
        ("daily", "每日游客统计", run_daily_mapreduce_remote, import_daily_result),
        ("hourly", "小时游客统计", run_hourly_mapreduce_remote, import_hourly_result),
        ("gate", "入口游客统计", run_gate_mapreduce_remote, import_gate_result),
    ]
    steps = []
    all_success = True

    upload_step = {
        "step": "upload_visitor_csv",
        "name": "上传游客 CSV 并替换 HDFS 输入文件",
        "success": False,
    }
    try:
        upload_step.update(
            {"success": True, "detail": upload_visitor_csv_to_hdfs_remote()}
        )
    except Exception as exc:
        upload_step["error"] = str(exc)
        steps.append(upload_step)
        return JsonResponse(
            {
                "code": 500,
                "message": "游客 CSV 上传 HDFS 失败",
                "success": False,
                "data": {"steps": steps},
            },
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )
    steps.append(upload_step)

    raw_import_step = {
        "step": "import_visitor_records",
        "name": "导入最新游客原始数据到 MySQL",
        "success": False,
    }
    try:
        raw_result = import_visitor_records_from_csv(clear_existing=True)
        raw_import_step.update(
            {
                "success": True,
                "imported_rows": raw_result.imported_rows,
                "skipped_rows": raw_result.skipped_rows,
            }
        )
    except Exception as exc:
        raw_import_step["error"] = str(exc)
        steps.append(raw_import_step)
        return JsonResponse(
            {
                "code": 500,
                "message": "游客原始数据导入 MySQL 失败",
                "success": False,
                "data": {"steps": steps},
            },
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )
    steps.append(raw_import_step)

    for job_key, job_name, run_remote, import_result in jobs:
        remote_step = {
            "step": f"run_{job_key}_mapreduce",
            "name": f"运行{job_name} MapReduce 并下载结果",
            "success": False,
        }
        try:
            remote_step.update({"success": True, "detail": run_remote()})
        except Exception as exc:
            remote_step["error"] = str(exc)
            steps.append(remote_step)
            steps.append(
                {
                    "step": f"import_{job_key}_result",
                    "name": f"导入{job_name}结果到 MySQL",
                    "success": False,
                    "skipped": True,
                    "error": "远程 MapReduce 或结果下载失败，未执行导入。",
                }
            )
            all_success = False
            continue

        steps.append(remote_step)
        import_step = {
            "step": f"import_{job_key}_result",
            "name": f"导入{job_name}结果到 MySQL",
            "success": False,
        }
        try:
            imported_rows = import_result()
            import_step.update({"success": True, "imported_rows": imported_rows})
        except Exception as exc:
            import_step["error"] = str(exc)
            all_success = False
        steps.append(import_step)

    return JsonResponse(
        {
            "code": 0 if all_success else 500,
            "message": "全部 MapReduce 作业及数据导入成功" if all_success else "部分步骤执行失败",
            "success": all_success,
            "data": {"steps": steps},
        },
        status=200 if all_success else 500,
        json_dumps_params={"ensure_ascii": False},
    )
