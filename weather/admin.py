from django.contrib import admin
from .models import (
    DailyWeatherStat,
    HourlyWeatherProfile,
    DailyComfortStat,
    DailyRiskStat,
    TopRiskDay,
    MapReduceSyncLog,
)


@admin.register(DailyWeatherStat)
class DailyWeatherStatAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "temperature_avg",
        "temperature_peak",
        "humidity_avg",
        "pm25_avg",
        "risk_warning",
    )
    list_filter = ("date",)
    search_fields = ("date", "risk_warning")
    ordering = ("date",)


@admin.register(HourlyWeatherProfile)
class HourlyWeatherProfileAdmin(admin.ModelAdmin):
    list_display = (
        "hour",
        "sample_count",
        "temperature_avg",
        "humidity_avg",
        "pm25_avg",
        "illumination_avg",
    )
    list_filter = ("hour",)
    ordering = ("hour",)


@admin.register(DailyComfortStat)
class DailyComfortStatAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "comfort_index_avg",
        "comfortable_count",
        "attention_count",
        "uncomfortable_count",
        "comfort_rate",
    )
    list_filter = ("date",)
    search_fields = ("date",)
    ordering = ("date",)


@admin.register(DailyRiskStat)
class DailyRiskStatAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "high_temp_count",
        "high_humidity_count",
        "pollution_count",
        "fire_risk_count",
        "risk_rate",
    )
    list_filter = ("date",)
    search_fields = ("date",)
    ordering = ("date",)


@admin.register(TopRiskDay)
class TopRiskDayAdmin(admin.ModelAdmin):
    list_display = (
        "rank",
        "date",
        "risk_score",
        "dangerous_count",
        "temperature_peak",
    )
    list_filter = ("rank",)
    search_fields = ("date",)
    ordering = ("rank",)


@admin.register(MapReduceSyncLog)
class MapReduceSyncLogAdmin(admin.ModelAdmin):
    list_display = ("status", "synced_at", "message")
    list_filter = ("status", "synced_at")
    ordering = ("-synced_at",)