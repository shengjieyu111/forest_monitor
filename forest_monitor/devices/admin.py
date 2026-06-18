from django.contrib import admin
from .models import DeviceWorstHealth


@admin.register(DeviceWorstHealth)
class WorstHealthAdmin(admin.ModelAdmin):
    list_display = ('rank_id', 'device', 'health_score', 'analysis_date')