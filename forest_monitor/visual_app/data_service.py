import math
from collections import Counter
from statistics import mean

from mapreduce_app.models import (
    DailyComfortStat,
    DailyRiskStat,
    DailyWeatherStat,
    HourlyWeatherProfile,
    MapReduceSyncLog,
    TopRiskDay,
)


def _round(value, digits=2):
    return round(value, digits)


def _warning_risk(warning):
    if warning == '正常':
        return '正常'
    warning_count = len([item for item in warning.split('、') if item])
    if '火灾预警' in warning and ('高温预警' in warning or 'PM2.5污染预警' in warning):
        return '高风险'
    if '火灾预警' in warning or warning_count >= 2:
        return '中风险'
    return '低风险'


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
    return {
        'mode': 'database',
        'online': True,
        'label': 'SQLite 计算结果库',
        'path': 'mapreduce_app_*',
        'host': 'db.sqlite3',
        'synced_at': latest.synced_at.isoformat() if latest else None,
    }


def build_dashboard_payload(start_date=None, end_date=None):
    daily_stats = list(_filter_queryset(
        DailyWeatherStat.objects.all(),
        start_date,
        end_date,
    ))
    if not daily_stats:
        return {
            'empty': True,
            'message': '数据库中没有 MapReduce 计算结果，请先执行同步命令',
            'source': _source_status(),
        }

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
    average_risk_rate = mean(
        [stat.risk_rate for stat in risk_stats.values()] or [0]
    )
    average_comfort_rate = mean(
        [stat.comfort_rate for stat in comfort_stats.values()] or [100]
    )
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

    return {
        'empty': False,
        'source': _source_status(),
        'meta': {
            'city': '北京鹫峰国家森林公园',
            'start_date': rows[0]['date'],
            'end_date': rows[-1]['date'],
            'record_count': len(rows),
            'updated_at': rows[-1]['date'],
            'sample_interval': '数据库持久化结果',
            'source_path': 'SQLite: mapreduce_app',
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
                'message': row['warning'],
                'temperature': row['temperature_avg'],
                'humidity': row['humidity_avg'],
                'pm25': row['pm25_avg'],
            }
            for row in reversed(warning_rows)
        ],
    }


def build_records_payload(
    page=1,
    page_size=20,
    keyword='',
    risk='',
    start_date=None,
    end_date=None,
):
    queryset = _filter_queryset(
        DailyWeatherStat.objects.all(),
        start_date,
        end_date,
    )
    rows = [_daily_row(stat) for stat in queryset]
    keyword = keyword.strip().lower()
    if keyword:
        rows = [
            row for row in rows
            if keyword in row['date'].lower()
            or keyword in row['warning'].lower()
        ]
    if risk:
        rows = [row for row in rows if row['risk'] == risk]

    total = len(rows)
    page_count = max(1, math.ceil(total / page_size))
    page = min(max(page, 1), page_count)
    start = (page - 1) * page_size

    return {
        'source': _source_status(),
        'page': page,
        'page_size': page_size,
        'page_count': page_count,
        'total': total,
        'results': rows[start:start + page_size],
    }
