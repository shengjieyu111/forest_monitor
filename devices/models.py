from django.db import models


# =========================
# 1. Device 原始表（修复版）
# =========================
class Device(models.Model):
    DEVICE_TYPE_CHOICES = [
        ("camera", "Camera"),
        ("sensor", "Sensor"),
    ]

    STATUS_CHOICES = [
        ("ONLINE", "Online"),
        ("FAULT", "Fault"),
        ("MAINTENANCE", "Maintenance"),
    ]

    LOCATION_CHOICES = [
        ("CORE_SCENIC", "Core Scenic"),
        ("FIRE_ZONE", "Fire Zone"),
        ("ENTRANCE_GATE", "Entrance Gate"),
        ("INFRA_AREA", "Infra Area"),
        ("TRAIL_ZONE", "Trail Zone"),
    ]

    device_id = models.CharField(max_length=64, unique=True)
    device_name = models.CharField(max_length=128)
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPE_CHOICES)
    sub_type = models.CharField(max_length=64, null=True, blank=True)

    longitude = models.FloatField()
    latitude = models.FloatField()

    location = models.CharField(max_length=32, choices=LOCATION_CHOICES)

    install_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["device_id"]),
            models.Index(fields=["status"]),
        ]


# =========================
# 2. WorkLog（不变）
# =========================
class DeviceWorkLog(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)

    cpu_usage = models.FloatField()
    memory_usage = models.FloatField()
    temperature = models.FloatField()
    power = models.FloatField()
    network_delay = models.FloatField()
    uptime = models.FloatField()

    record_time = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["device", "record_time"]),
        ]


# =========================
# 3. Fault（不变）
# =========================
class DeviceFault(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)

    fault_type = models.CharField(max_length=64)
    fault_level = models.IntegerField()
    is_resolved = models.BooleanField(default=False)

    record_time = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["fault_type"]),
            models.Index(fields=["record_time"]),
        ]


# =========================
# 4. Overview（Python）
# =========================
class DeviceOverview(models.Model):
    total_count = models.IntegerField()
    online_count = models.IntegerField()
    fault_count = models.IntegerField()
    maintenance_count = models.IntegerField()

    online_rate = models.FloatField()
    fault_rate = models.FloatField()

    analysis_date = models.DateField(unique=True)

# =========================
# 5. Fault统计（MR1）
# =========================
class FaultTypeDistribution(models.Model):
    fault_type = models.CharField(max_length=64)

    fault_count = models.IntegerField()

    device_type = models.CharField(max_length=32, null=True, blank=True)
    location = models.CharField(max_length=32, null=True, blank=True)

    analysis_date = models.DateField()

    class Meta:
        unique_together = (
            "fault_type",
            "device_type",
            "location",
            "analysis_date"
        )

# =========================
# 6. Health（MR2）
# =========================
class DeviceHealthAnalysis(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)

    health_score = models.FloatField()
    analysis_date = models.DateField()

    class Meta:
        unique_together = ("device", "analysis_date")
        indexes = [
            models.Index(fields=["analysis_date"]),
        ]

# =========================
# 7. Fault时空区域统计（MR3）
# =========================
class FaultTimeRegionAnalysis(models.Model):

    # 时间维度（可以是天 / 小时 / 月）
    analysis_date = models.DateField()

    # 区域维度（ENTRANCE / CORE / FIRE / TRAIL / INFRA）
    location = models.CharField(max_length=32)

    # 故障类型
    fault_type = models.CharField(max_length=64)

    # 统计值（MR输出核心）
    fault_count = models.IntegerField()

    # 可选增强字段（推荐保留）
    device_type = models.CharField(max_length=32, null=True, blank=True)

    class Meta:
        unique_together = (
            "analysis_date",
            "location",
            "fault_type",
            "device_type"
        )


# =========================
# 8. 设备分析（MR4）
# =========================
class Device7DayAnalysis(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)

    stat_date = models.DateField()

    avg_cpu = models.FloatField()
    avg_memory = models.FloatField()
    avg_temperature = models.FloatField()
    avg_power = models.FloatField()
    avg_network_delay = models.FloatField()

    health_score = models.FloatField()

    analysis_date = models.DateField()

    class Meta:
        unique_together = ("device", "stat_date")
        indexes = [
            models.Index(fields=["stat_date"]),
        ]