from datetime import date
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction

from .models import (
    DailyComfortStat,
    DailyRiskStat,
    DailyWeatherStat,
    HourlyWeatherProfile,
    MapReduceSyncLog,
    TopRiskDay,
)


RESULT_PATHS = {
    'daily': '/waether/output/part-r-00000',
    'hourly': '/waether/hourly_output/part-r-00000',
    'risk': '/waether/risk_output/part-r-00000',
    'comfort': '/waether/comfort_output/part-r-00000',
    'topn': '/waether/topn_output/part-r-00000',
}


def _webhdfs_url(path):
    return (
        f"http://{settings.HDFS_WEB_HOST}:{settings.HDFS_WEB_PORT}"
        f"/webhdfs/v1{quote(path, safe='/')}?op=OPEN&user.name={quote(settings.HDFS_USER)}"
    )


def read_hdfs_result(path):
    request = Request(
        _webhdfs_url(path),
        headers={'User-Agent': 'forest-monitor-db-sync/1.0'},
    )
    with urlopen(request, timeout=settings.HDFS_TIMEOUT) as response:
        return response.read().decode('utf-8')


def parse_key_values(line):
    key, values_text = line.split('\t', 1)
    values = {}
    for item in values_text.split(','):
        name, value = item.split('=', 1)
        values[name.strip()] = value.strip()
    return key.strip(), values


def _sync_daily(content):
    synced_dates = []
    for line in content.splitlines():
        if not line.strip():
            continue
        key, values = parse_key_values(line)
        stat_date = date.fromisoformat(key)
        DailyWeatherStat.objects.update_or_create(
            date=stat_date,
            defaults={
                'temperature_avg': float(values['temp_avg']),
                'temperature_peak': float(values['temp_peak']),
                'humidity_avg': float(values['humidity_avg']),
                'humidity_peak': float(values['humidity_peak']),
                'pm25_avg': float(values['pm25_avg']),
                'pm25_peak': float(values['pm25_peak']),
                'illumination_avg': float(values['illumination_avg']),
                'illumination_peak': float(values['illumination_peak']),
                'risk_warning': values.get('risk_warning', '正常'),
            },
        )
        synced_dates.append(stat_date)
    DailyWeatherStat.objects.exclude(date__in=synced_dates).delete()
    return len(synced_dates)


def _sync_hourly(content):
    synced_hours = []
    for line in content.splitlines():
        if not line.strip():
            continue
        key, values = parse_key_values(line)
        hour = int(key)
        HourlyWeatherProfile.objects.update_or_create(
            hour=hour,
            defaults={
                'sample_count': int(values['sample_count']),
                'temperature_avg': float(values['temp_avg']),
                'humidity_avg': float(values['humidity_avg']),
                'pm25_avg': float(values['pm25_avg']),
                'illumination_avg': float(values['illumination_avg']),
            },
        )
        synced_hours.append(hour)
    HourlyWeatherProfile.objects.exclude(hour__in=synced_hours).delete()
    return len(synced_hours)


def _sync_risk(content):
    synced_dates = []
    for line in content.splitlines():
        if not line.strip():
            continue
        key, values = parse_key_values(line)
        stat_date = date.fromisoformat(key)
        DailyRiskStat.objects.update_or_create(
            date=stat_date,
            defaults={
                'sample_count': int(values['sample_count']),
                'high_temp_count': int(values['high_temp_count']),
                'high_humidity_count': int(values['high_humidity_count']),
                'pollution_count': int(values['pollution_count']),
                'fire_risk_count': int(values['fire_risk_count']),
                'normal_count': int(values['normal_count']),
                'risk_rate': float(values['risk_rate']),
            },
        )
        synced_dates.append(stat_date)
    DailyRiskStat.objects.exclude(date__in=synced_dates).delete()
    return len(synced_dates)


def _sync_comfort(content):
    synced_dates = []
    for line in content.splitlines():
        if not line.strip():
            continue
        key, values = parse_key_values(line)
        stat_date = date.fromisoformat(key)
        DailyComfortStat.objects.update_or_create(
            date=stat_date,
            defaults={
                'sample_count': int(values['sample_count']),
                'comfort_index_avg': float(values['comfort_index_avg']),
                'comfortable_count': int(values['comfortable_count']),
                'attention_count': int(values['attention_count']),
                'uncomfortable_count': int(values['uncomfortable_count']),
                'comfort_rate': float(values['comfort_rate']),
            },
        )
        synced_dates.append(stat_date)
    DailyComfortStat.objects.exclude(date__in=synced_dates).delete()
    return len(synced_dates)


def _sync_topn(content):
    synced_ranks = []
    for line in content.splitlines():
        if not line.strip():
            continue
        key, values = parse_key_values(line)
        rank = int(key)
        TopRiskDay.objects.update_or_create(
            rank=rank,
            defaults={
                'date': date.fromisoformat(values['date']),
                'risk_score': float(values['risk_score']),
                'dangerous_count': int(values['dangerous_count']),
                'temperature_peak': float(values['temp_peak']),
                'humidity_low': float(values['humidity_low']),
                'pm25_peak': float(values['pm25_peak']),
                'illumination_peak': float(values['illumination_peak']),
            },
        )
        synced_ranks.append(rank)
    TopRiskDay.objects.exclude(rank__in=synced_ranks).delete()
    return len(synced_ranks)


SYNC_HANDLERS = {
    'daily': _sync_daily,
    'hourly': _sync_hourly,
    'risk': _sync_risk,
    'comfort': _sync_comfort,
    'topn': _sync_topn,
}


def sync_result(job_type):
    source_path = RESULT_PATHS[job_type]
    try:
        content = read_hdfs_result(source_path)
        with transaction.atomic():
            count = SYNC_HANDLERS[job_type](content)
            MapReduceSyncLog.objects.create(
                job_type=job_type,
                source_path=source_path,
                record_count=count,
                status='success',
            )
        return count
    except Exception as error:
        MapReduceSyncLog.objects.create(
            job_type=job_type,
            source_path=source_path,
            status='failed',
            message=str(error),
        )
        raise


def sync_all_results():
    return {
        job_type: sync_result(job_type)
        for job_type in RESULT_PATHS
    }
