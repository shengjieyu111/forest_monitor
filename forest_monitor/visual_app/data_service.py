import json
import math
import time
from collections import Counter
from pathlib import Path
from statistics import mean
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings


HDFS_HOST = getattr(settings, 'HDFS_WEB_HOST', 'hd0')
HDFS_PORT = getattr(settings, 'HDFS_WEB_PORT', 50070)
HDFS_OUTPUT_PATH = getattr(settings, 'HDFS_OUTPUT_PATH', '/waether/output')
HDFS_USER = getattr(settings, 'HDFS_USER', 'root')
HDFS_PART_FILE = getattr(settings, 'HDFS_PART_FILE', 'part-r-00000')
HDFS_TIMEOUT = getattr(settings, 'HDFS_TIMEOUT', 20)
CACHE_SECONDS = 30
CACHE_PATH = Path(settings.BASE_DIR) / 'visual_app' / 'hdfs_result_cache.json'

_memory_cache = {'loaded_at': 0.0, 'rows': None, 'status': None}


def _round(value, digits=2):
    return round(value, digits)


def _webhdfs_url(path, operation):
    encoded_path = quote(path, safe='/')
    return (
        f'http://{HDFS_HOST}:{HDFS_PORT}/webhdfs/v1{encoded_path}'
        f'?op={operation}&user.name={quote(HDFS_USER)}'
    )


def _read_url(url):
    request = Request(url, headers={'User-Agent': 'forest-monitor-dashboard/1.0'})
    with urlopen(request, timeout=HDFS_TIMEOUT) as response:
        return response.read().decode('utf-8')


def _parse_result_line(line):
    date, values_text = line.split('\t', 1)
    values = {}
    for item in values_text.split(','):
        key, value = item.split('=', 1)
        values[key.strip()] = value.strip()

    warning = values.get('risk_warning', '正常')
    return {
        'date': date.strip(),
        'temperature_avg': float(values['temp_avg']),
        'temperature_max': float(values['temp_peak']),
        'humidity_avg': float(values['humidity_avg']),
        'humidity_max': float(values['humidity_peak']),
        'pm25_avg': float(values['pm25_avg']),
        'pm25_max': float(values['pm25_peak']),
        'illumination_avg': float(values['illumination_avg']),
        'illumination_max': float(values['illumination_peak']),
        'warning': warning,
        'risk': _warning_risk(warning),
    }


def _warning_risk(warning):
    if warning == '正常':
        return '正常'
    warning_count = len([item for item in warning.split('、') if item])
    if '火灾预警' in warning and ('高温预警' in warning or 'PM2.5污染预警' in warning):
        return '高风险'
    if '火灾预警' in warning or warning_count >= 2:
        return '中风险'
    return '低风险'


def _write_cache(rows):
    CACHE_PATH.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def _read_cache():
    if not CACHE_PATH.exists():
        return None
    return json.loads(CACHE_PATH.read_text(encoding='utf-8'))


def get_hdfs_daily_stats(force=False):
    now = time.monotonic()
    if (
        not force
        and _memory_cache['rows'] is not None
        and now - _memory_cache['loaded_at'] < CACHE_SECONDS
    ):
        return _memory_cache['rows'], _memory_cache['status']

    file_path = f"{HDFS_OUTPUT_PATH.rstrip('/')}/{HDFS_PART_FILE}"
    try:
        content = _read_url(_webhdfs_url(file_path, 'OPEN'))
        rows = [
            _parse_result_line(line)
            for line in content.splitlines()
            if line.strip()
        ]
        rows.sort(key=lambda row: row['date'])
        if not rows:
            raise ValueError('HDFS MapReduce 结果文件为空')
        _write_cache(rows)
        status = {
            'mode': 'hdfs',
            'online': True,
            'label': 'HDFS 实时结果',
            'path': file_path,
            'host': f'{HDFS_HOST}:{HDFS_PORT}',
        }
    except Exception as error:
        rows = _read_cache()
        if not rows:
            raise RuntimeError(f'无法读取 HDFS 结果：{error}') from error
        status = {
            'mode': 'cache',
            'online': False,
            'label': 'HDFS 缓存结果',
            'path': file_path,
            'host': f'{HDFS_HOST}:{HDFS_PORT}',
            'error': str(error),
        }

    _memory_cache.update({'loaded_at': now, 'rows': rows, 'status': status})
    return rows, status


def _filter_rows(rows, start_date=None, end_date=None):
    if start_date:
        rows = [row for row in rows if row['date'] >= start_date]
    if end_date:
        rows = [row for row in rows if row['date'] <= end_date]
    return rows


def build_dashboard_payload(start_date=None, end_date=None, force=False):
    all_rows, source = get_hdfs_daily_stats(force=force)
    rows = _filter_rows(all_rows, start_date, end_date)
    if not rows:
        return {
            'empty': True,
            'message': '所选日期范围内没有 HDFS 聚合结果',
            'source': source,
        }

    risk_counts = Counter(row['risk'] for row in rows)
    warning_rows = [row for row in rows if row['warning'] != '正常']
    latest = rows[-1]
    health_score = max(
        0,
        round(
            100
            - risk_counts['低风险'] * 5
            - risk_counts['中风险'] * 12
            - risk_counts['高风险'] * 22
        ),
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
        metric_values = [
            row['temperature_avg'],
            row['humidity_avg'],
            row['pm25_avg'],
            row['illumination_avg'] / 1000,
        ]
        for metric_index, value in enumerate(metric_values):
            heatmap.append([date_index, metric_index, _round(value)])

    return {
        'empty': False,
        'source': source,
        'meta': {
            'city': '北京鹫峰国家森林公园',
            'start_date': rows[0]['date'],
            'end_date': rows[-1]['date'],
            'record_count': len(rows),
            'updated_at': rows[-1]['date'],
            'sample_interval': 'MapReduce 日聚合',
            'source_path': source['path'],
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
        'peak_comparison': [
            {
                'date': row['date'],
                'temperature': row['temperature_max'],
                'humidity': row['humidity_max'],
                'pm25': row['pm25_max'],
                'illumination': _round(row['illumination_max'] / 1000),
            }
            for row in rows
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
                _round(len(warning_rows) / len(rows) * 100),
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
    rows, source = get_hdfs_daily_stats()
    rows = _filter_rows(rows, start_date, end_date)
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
        'source': source,
        'page': page,
        'page_size': page_size,
        'page_count': page_count,
        'total': total,
        'results': rows[start:start + page_size],
    }
