from django.contrib import admin

from .models import MapReduceRun


@admin.register(MapReduceRun)
class MapReduceRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'input_path', 'auto_refresh', 'created_at', 'finished_at')
    readonly_fields = ('created_at', 'started_at', 'finished_at', 'output_log')
