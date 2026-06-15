from django.contrib import admin

from .models import (
    DailyComfortStat,
    DailyRiskStat,
    DailyWeatherStat,
    HourlyWeatherProfile,
    MapReduceSyncLog,
    TopRiskDay,
)


@admin.register(DailyWeatherStat)
class DailyWeatherStatAdmin(admin.ModelAdmin):
    list_display = ('date', 'temperature_avg', 'humidity_avg', 'pm25_avg', 'risk_warning')
    ordering = ('-date',)


@admin.register(HourlyWeatherProfile)
class HourlyWeatherProfileAdmin(admin.ModelAdmin):
    list_display = ('hour', 'sample_count', 'temperature_avg', 'humidity_avg', 'pm25_avg')


@admin.register(DailyRiskStat)
class DailyRiskStatAdmin(admin.ModelAdmin):
    list_display = ('date', 'risk_rate', 'fire_risk_count', 'pollution_count', 'normal_count')
    ordering = ('-date',)


@admin.register(DailyComfortStat)
class DailyComfortStatAdmin(admin.ModelAdmin):
    list_display = ('date', 'comfort_index_avg', 'comfort_rate', 'uncomfortable_count')
    ordering = ('-date',)


@admin.register(MapReduceSyncLog)
class MapReduceSyncLogAdmin(admin.ModelAdmin):
    list_display = ('job_type', 'source_path', 'record_count', 'status', 'synced_at')
    readonly_fields = ('synced_at',)


@admin.register(TopRiskDay)
class TopRiskDayAdmin(admin.ModelAdmin):
    list_display = ('rank', 'date', 'risk_score', 'dangerous_count', 'temperature_peak', 'pm25_peak')
    ordering = ('rank',)
