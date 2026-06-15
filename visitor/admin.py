from django.contrib import admin

from .models import VisitorDailyStat, VisitorGateStat, VisitorHourlyStat, VisitorRecord


@admin.register(VisitorRecord)
class VisitorRecordAdmin(admin.ModelAdmin):
    list_display = ("visit_time", "gate", "visitor_count", "ticket_type", "weather")
    list_filter = ("gate", "ticket_type", "weather", "visit_time")
    search_fields = ("gate", "ticket_type", "weather")
    date_hierarchy = "visit_time"


@admin.register(VisitorDailyStat)
class VisitorDailyStatAdmin(admin.ModelAdmin):
    list_display = ("stat_date", "total_count", "created_at")
    date_hierarchy = "stat_date"


@admin.register(VisitorHourlyStat)
class VisitorHourlyStatAdmin(admin.ModelAdmin):
    list_display = ("hour", "total_count", "created_at")


@admin.register(VisitorGateStat)
class VisitorGateStatAdmin(admin.ModelAdmin):
    list_display = ("gate", "total_count", "created_at")
    search_fields = ("gate",)
