from django.contrib import admin
from .models import Device, DeviceWorkLog, DeviceFault


# =========================
# 设备基础信息
# =========================
@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = (
        "device_id",
        "device_name",
        "device_type",
        "sub_type",
        "location",
        "status",
        "install_date",
    )

    list_filter = (
        "device_type",
        "sub_type",
        "location",
        "status",
    )

    search_fields = (
        "device_id",
        "device_name",
    )

    ordering = ("device_id",)


# =========================
# 工作日志
# =========================
@admin.register(DeviceWorkLog)
class DeviceWorkLogAdmin(admin.ModelAdmin):
    list_display = (
        "device",
        "cpu_usage",
        "memory_usage",
        "temperature",
        "power",
        "network_delay",
        "uptime",
        "record_time",
    )

    list_filter = ("record_time", "device__device_type")

    search_fields = ("device__device_id",)

    ordering = ("-record_time",)


# =========================
# 故障日志
# =========================
@admin.register(DeviceFault)
class DeviceFaultAdmin(admin.ModelAdmin):
    list_display = (
        "device",
        "fault_type",
        "fault_level",
        "is_resolved",
        "record_time",
    )

    list_filter = (
        "fault_type",
        "fault_level",
        "is_resolved",
        "record_time",
        "device__location",
        "device__device_type",
    )

    search_fields = (
        "device__device_id",
        "fault_type",
    )

    ordering = ("-record_time",)