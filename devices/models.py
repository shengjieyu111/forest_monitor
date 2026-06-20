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
    # 显式声明主键，与数据库 AUTO_INCREMENT 对应
    id = models.BigAutoField(primary_key=True)

    fault_type = models.CharField(max_length=64)
    fault_count = models.IntegerField()
    analysis_date = models.DateField()
    device_type = models.CharField(max_length=32, null=True, blank=True)
    location = models.CharField(max_length=32, null=True, blank=True)

    class Meta:
        db_table = 'devices_faulttypedistribution'
        unique_together = (
            "fault_type",
            "device_type",
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
    # 显式声明主键，与数据库 AUTO_INCREMENT 对应
    id = models.BigAutoField(primary_key=True)

    analysis_date = models.DateField()
    location = models.CharField(max_length=32)
    fault_type = models.CharField(max_length=64)
    fault_count = models.IntegerField()
    device_type = models.CharField(max_length=32, null=True, blank=True)
    fault_level = models.IntegerField(default=1)

    class Meta:
        db_table = 'devices_faulttimeregionanalysis'
        unique_together = (
            "analysis_date",
            "location",
            "fault_type",
            "device_type",
            "fault_level"
        )

# =========================
# 8. 设备分析（MR4）
# =========================
class DeviceWorkAnalysis(models.Model):
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