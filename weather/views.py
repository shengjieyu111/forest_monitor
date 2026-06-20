import math
import traceback
from collections import Counter
from statistics import mean

from django.conf import settings
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import (
    DailyComfortStat,
    DailyRiskStat,
    DailyWeatherStat,
    HourlyWeatherProfile,
    MapReduceSyncLog,
    TopRiskDay,
)
from .services import (
    get_weather_health_summary,
    load_comfort_to_mysql,
    load_hourly_profile_to_mysql,
    load_risk_to_mysql,
    load_topn_to_mysql,
    load_weather_stats_to_mysql,
    run_mr_daily_comfort,
    run_mr_daily_risk,
    run_mr_hourly_profile,
    run_mr_risk_topn,
    run_mr_weather_stats,
    upload_csv_to_hdfs,
)


# =========================
# 工具函数
# =========================
def _round(value, digits=2):
    return round(value, digits)


def _warning_risk(warning):
    if not warning or warning in ('正常', 'normal', 'None', ''):
        return '正常'

    warning = str(warning)
    # 中英文关键词映射
    has_fire = any(k in warning for k in ['火灾预警', 'fire_warning', 'fire_risk'])
    has_high_temp = any(k in warning for k in ['高温预警', 'high_temp', 'high_temperature'])
    has_high_humidity = any(k in warning for k in ['高湿预警', 'high_humidity'])
    has_pm25 = any(k in warning for k in ['PM2.5污染预警', 'pm25', 'pollution'])
    has_warning = has_fire or has_high_temp or has_high_humidity or has_pm25

    if not has_warning:
        return '正常'

    # 计算有效预警数量
    warning_count = sum([has_fire, has_high_temp, has_high_humidity, has_pm25])

    # 高风险：火灾预警 + (高温预警 或 PM2.5污染预警)
    if has_fire and (has_high_temp or has_pm25):
        return '高风险'
    # 中风险：火灾预警 或 2个及以上预警
    if has_fire or warning_count >= 2:
        return '中风险'
    return '低风险'


def _warning_to_chinese(warning):
    """将英文预警转换为中文"""
    if not warning or warning in ('正常', 'normal', 'None', ''):
        return '正常'

    warning = str(warning)
    parts = []

    if any(k in warning for k in ['火灾预警', 'fire_warning', 'fire_risk']):
        parts.append('火灾预警')
    if any(k in warning for k in ['高温预警', 'high_temp', 'high_temperature']):
        parts.append('高温预警')
    if any(k in warning for k in ['高湿预警', 'high_humidity']):
        parts.append('高湿预警')
    if any(k in warning for k in ['PM2.5污染预警', 'pm25', 'pollution']):
        parts.append('PM2.5污染预警')

    return '、'.join(parts) if parts else '正常'


def _daily_row(stat):
    warning = stat.risk_warning
    return {
        'date': stat.date.isoformat(),
        'temperature_avg': stat.temperature_avg,
        'temperature_max': stat.temperature_peak,
        'humidity_avg': stat.humidity_avg,
        'humidity_max': stat.humidity_peak,
        'pm25_avg': stat.pm25_avg,
        'pm25_max': stat.pm25_peak,
        'illumination_avg': stat.illumination_avg,
        'illumination_max': stat.illumination_peak,
        'warning': warning,
        'risk': _warning_risk(warning),
    }


def _filter_queryset(queryset, start_date=None, end_date=None):
    if start_date:
        queryset = queryset.filter(date__gte=start_date)
    if end_date:
        queryset = queryset.filter(date__lte=end_date)
    return queryset


def _source_status():
    latest = MapReduceSyncLog.objects.filter(status='success').first()
    database = settings.DATABASES['default']
    return {
        'mode': 'database',
        'online': True,
        'label': 'MySQL 计算结果库',
        'path': 'mapreduce_app_*',
        'host': f"{database.get('HOST', '127.0.0.1')}:{database.get('PORT', '3306')}",
        'synced_at': latest.synced_at.isoformat() if latest else None,
    }


def api_response(data, message="success", code=0):
    """统一的 API 响应包装"""
    return JsonResponse(
        {"code": code, "message": message, "data": data},
        json_dumps_params={"ensure_ascii": False},
    )


# =========================
# 1. 仪表盘页面
# =========================
def weather_dashboard(request):
    return render(request, "weather_dashboard.html", {"page": "weather"})


# =========================
# 2. 概览数据（整合所有）
# =========================
def weather_overview_api(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    daily_stats = list(_filter_queryset(
        DailyWeatherStat.objects.all(),
        start_date,
        end_date,
    ))
    if not daily_stats:
        return api_response({
            'empty': True,
            'message': '数据库中没有 MapReduce 计算结果，请先执行同步命令',
            'source': _source_status(),
        })

    rows = [_daily_row(stat) for stat in daily_stats]
    dates = [stat.date for stat in daily_stats]
    hourly_stats = list(HourlyWeatherProfile.objects.all())
    risk_stats = {
        stat.date: stat
        for stat in DailyRiskStat.objects.filter(date__in=dates)
    }
    comfort_stats = {
        stat.date: stat
        for stat in DailyComfortStat.objects.filter(date__in=dates)
    }
    top_risk_days = list(TopRiskDay.objects.all())

    risk_counts = Counter(row['risk'] for row in rows)
    warning_rows = [row for row in rows if row['warning'] != '正常']
    latest = rows[-1]
    average_risk_rate = float(mean(
        [stat.risk_rate for stat in risk_stats.values()] or [0]
    ))
    average_comfort_rate = float(mean(
        [stat.comfort_rate for stat in comfort_stats.values()] or [100]
    ))
    health_score = max(
        0,
        round(100 - average_risk_rate * 0.55 - (100 - average_comfort_rate) * 0.25),
    )

    temperature_distribution = [
        {'name': '<24℃', 'value': sum(row['temperature_avg'] < 24 for row in rows)},
        {'name': '24-25℃', 'value': sum(24 <= row['temperature_avg'] < 25 for row in rows)},
        {'name': '25-26℃', 'value': sum(25 <= row['temperature_avg'] < 26 for row in rows)},
        {'name': '≥26℃', 'value': sum(row['temperature_avg'] >= 26 for row in rows)},
    ]

    heatmap_metrics = ['平均温度', '平均湿度', '平均PM2.5', '平均光照(k)']
    heatmap = []
    for date_index, row in enumerate(rows):
        values = [
            row['temperature_avg'],
            row['humidity_avg'],
            row['pm25_avg'],
            row['illumination_avg'] / 1000,
        ]
        for metric_index, value in enumerate(values):
            heatmap.append([date_index, metric_index, _round(value)])

    risk_detail = []
    comfort_detail = []
    for stat in daily_stats:
        risk = risk_stats.get(stat.date)
        comfort = comfort_stats.get(stat.date)
        if risk:
            risk_detail.append({
                'date': stat.date.isoformat(),
                'high_temp_count': risk.high_temp_count,
                'high_humidity_count': risk.high_humidity_count,
                'pollution_count': risk.pollution_count,
                'fire_risk_count': risk.fire_risk_count,
                'normal_count': risk.normal_count,
                'risk_rate': risk.risk_rate,
            })
        if comfort:
            comfort_detail.append({
                'date': stat.date.isoformat(),
                'comfort_index_avg': comfort.comfort_index_avg,
                'comfortable_count': comfort.comfortable_count,
                'attention_count': comfort.attention_count,
                'uncomfortable_count': comfort.uncomfortable_count,
                'comfort_rate': comfort.comfort_rate,
            })

    data = {
        'empty': False,
        'source': _source_status(),
        'meta': {
            'city': '北京鹫峰国家森林公园',
            'start_date': rows[0]['date'],
            'end_date': rows[-1]['date'],
            'record_count': len(rows),
            'updated_at': rows[-1]['date'],
            'sample_interval': '数据库持久化结果',
            'source_path': 'MySQL: mapreduce_app',
        },
        'kpis': {
            'temperature_avg': _round(mean(row['temperature_avg'] for row in rows)),
            'temperature_max': _round(max(row['temperature_max'] for row in rows), 1),
            'humidity_avg': _round(mean(row['humidity_avg'] for row in rows)),
            'pm25_avg': _round(mean(row['pm25_avg'] for row in rows)),
            'illumination_max': _round(max(row['illumination_max'] for row in rows), 1),
            'risk_events': len(warning_rows),
            'high_risk_events': risk_counts['高风险'],
            'health_score': health_score,
            'risk_rate': _round(average_risk_rate),
            'comfort_rate': _round(average_comfort_rate),
        },
        'latest': {
            'time': latest['date'],
            'temperature': latest['temperature_avg'],
            'humidity': latest['humidity_avg'],
            'pm25': latest['pm25_avg'],
            'illumination': latest['illumination_avg'],
            'risk': latest['risk'],
            'warning': latest['warning'],
        },
        'trend': {
            'times': [row['date'] for row in rows],
            'temperature': [row['temperature_avg'] for row in rows],
            'temperature_peak': [row['temperature_max'] for row in rows],
            'humidity': [row['humidity_avg'] for row in rows],
            'humidity_peak': [row['humidity_max'] for row in rows],
            'pm25': [row['pm25_avg'] for row in rows],
            'pm25_peak': [row['pm25_max'] for row in rows],
            'illumination': [row['illumination_avg'] for row in rows],
            'illumination_peak': [row['illumination_max'] for row in rows],
        },
        'daily': rows,
        'hourly': [
            {
                'hour': f'{stat.hour:02d}:00',
                'sample_count': stat.sample_count,
                'temperature': stat.temperature_avg,
                'humidity': stat.humidity_avg,
                'pm25': stat.pm25_avg,
                'illumination': stat.illumination_avg,
            }
            for stat in hourly_stats
        ],
        'risk_detail': risk_detail,
        'comfort_detail': comfort_detail,
        'topn': [
            {
                'rank': stat.rank,
                'date': stat.date.isoformat(),
                'risk_score': stat.risk_score,
                'dangerous_count': stat.dangerous_count,
                'temperature_peak': stat.temperature_peak,
                'humidity_low': stat.humidity_low,
                'pm25_peak': stat.pm25_peak,
                'illumination_peak': stat.illumination_peak,
            }
            for stat in top_risk_days
        ],
        'risk_distribution': [
            {'name': name, 'value': risk_counts[name]}
            for name in ('正常', '低风险', '中风险', '高风险')
        ],
        'temperature_distribution': temperature_distribution,
        'scatter': [
            [
                row['temperature_avg'],
                row['humidity_avg'],
                row['pm25_avg'],
                row['date'],
                row['risk'],
            ]
            for row in rows
        ],
        'heatmap': heatmap,
        'heatmap_dates': [row['date'] for row in rows],
        'heatmap_metrics': heatmap_metrics,
        'radar': {
            'values': [
                _round(mean(row['temperature_avg'] for row in rows)),
                _round(mean(row['humidity_avg'] for row in rows)),
                _round(mean(row['pm25_avg'] for row in rows)),
                _round(mean(row['illumination_avg'] for row in rows) / 1000),
                _round(average_risk_rate),
            ],
        },
        'alerts': [
            {
                'time': row['date'],
                'level': row['risk'],
                'message': _warning_to_chinese(row['warning']),
                'temperature': row['temperature_avg'],
                'humidity': row['humidity_avg'],
                'pm25': row['pm25_avg'],
            }
            for row in reversed(warning_rows)
        ],
    }
    return api_response(data)


# =========================
# 3. 分页记录查询
# =========================
def weather_records_api(request):
    try:
        page_number = max(int(request.GET.get('page', 1)), 1)
        page_size = min(max(int(request.GET.get('page_size', 20)), 1), 200)
    except ValueError:
        return JsonResponse(
            {"code": 400, "message": "page 和 page_size 必须是整数", "data": None},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    risk = request.GET.get('risk', '').strip()
    keyword = request.GET.get('keyword', '').strip().lower()

    queryset = _filter_queryset(DailyWeatherStat.objects.all(), start_date, end_date)
    rows = [_daily_row(stat) for stat in queryset]

    if keyword:
        rows = [
            row for row in rows
            if keyword in row['date'].lower()
            or keyword in row['warning'].lower()
        ]
    if risk:
        rows = [row for row in rows if row['risk'] == risk]

    paginator = Paginator(rows, page_size)
    page = paginator.get_page(page_number)

    return api_response({
        'items': list(page.object_list),
        'page': page.number,
        'page_size': page_size,
        'total': paginator.count,
        'total_pages': paginator.num_pages,
        'source': _source_status(),
    })


# =========================
# 4. 每日气象统计 API
# =========================
def weather_daily_stat_api(request):
    rows = list(DailyWeatherStat.objects.order_by('date'))
    return api_response({
        'labels': [row.date.isoformat() for row in rows],
        'temperature_avg': [row.temperature_avg for row in rows],
        'temperature_peak': [row.temperature_peak for row in rows],
        'humidity_avg': [row.humidity_avg for row in rows],
        'pm25_avg': [row.pm25_avg for row in rows],
        'illumination_avg': [row.illumination_avg for row in rows],
        'risk_warning': [row.risk_warning for row in rows],
    })


# =========================
# 5. 小时气象分布 API
# =========================
def weather_hourly_stat_api(request):
    rows = list(HourlyWeatherProfile.objects.order_by('hour'))
    return api_response({
        'labels': [f"{row.hour:02d}:00" for row in rows],
        'temperature': [row.temperature_avg for row in rows],
        'humidity': [row.humidity_avg for row in rows],
        'pm25': [row.pm25_avg for row in rows],
        'illumination': [row.illumination_avg for row in rows],
        'sample_count': [row.sample_count for row in rows],
    })


# =========================
# 6. 舒适度统计 API
# =========================
def weather_comfort_stat_api(request):
    rows = list(DailyComfortStat.objects.order_by('date'))
    return api_response({
        'labels': [row.date.isoformat() for row in rows],
        'comfort_index_avg': [row.comfort_index_avg for row in rows],
        'comfortable_count': [row.comfortable_count for row in rows],
        'attention_count': [row.attention_count for row in rows],
        'uncomfortable_count': [row.uncomfortable_count for row in rows],
        'comfort_rate': [row.comfort_rate for row in rows],
    })


# =========================
# 7. 风险统计 API
# =========================
def weather_risk_stat_api(request):
    rows = list(DailyRiskStat.objects.order_by('date'))
    return api_response({
        'labels': [row.date.isoformat() for row in rows],
        'high_temp_count': [row.high_temp_count for row in rows],
        'high_humidity_count': [row.high_humidity_count for row in rows],
        'pollution_count': [row.pollution_count for row in rows],
        'fire_risk_count': [row.fire_risk_count for row in rows],
        'normal_count': [row.normal_count for row in rows],
        'risk_rate': [row.risk_rate for row in rows],
    })


# =========================
# 8. 风险 TopN API
# =========================
def weather_topn_api(request):
    rows = list(TopRiskDay.objects.order_by('rank'))
    return api_response([
        {
            'rank': row.rank,
            'date': row.date.isoformat(),
            'risk_score': row.risk_score,
            'dangerous_count': row.dangerous_count,
            'temperature_peak': row.temperature_peak,
            'humidity_low': row.humidity_low,
            'pm25_peak': row.pm25_peak,
            'illumination_peak': row.illumination_peak,
        }
        for row in rows
    ])


# =========================
# 9. 健康摘要 API
# =========================
def weather_health_summary_api(request):
    return api_response(get_weather_health_summary())


# =========================
# 10. MapReduce 触发接口
# =========================
@csrf_exempt
@require_POST
def run_weather_analysis_api(request):
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
            print(f"[EXCEPTION] {job_key}: {exc}\n{traceback.format_exc()}")
            all_success = False
        steps.append(step)

        if not all_success and job_key != "upload":
            break

    if not all_success:
        MapReduceSyncLog.objects.create(status="failed", message="MR执行失败")
        return JsonResponse(
            {
                "code": 500,
                "message": "部分 MapReduce 作业执行失败",
                "success": False,
                "data": {"steps": steps},
            },
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )

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
            print(f"[EXCEPTION] {job_key}: {exc}\n{traceback.format_exc()}")
            all_success = False
        steps.append(step)

        if not all_success:
            break

    if all_success:
        MapReduceSyncLog.objects.create(status="success", message="气象数据同步完成")
    else:
        MapReduceSyncLog.objects.create(status="failed", message="部分数据导入失败")

    report = get_weather_health_summary()
    return JsonResponse(
        {
            "code": 0 if all_success else 500,
            "message": "全部 MapReduce 作业及数据导入成功" if all_success else "部分步骤执行失败",
            "success": all_success,
            "data": {"steps": steps, "report": report},
        },
        status=200 if all_success else 500,
        json_dumps_params={"ensure_ascii": False},
    )