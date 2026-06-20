from django.db import models


class MapReduceSyncLog(models.Model):
    status = models.CharField(max_length=20, choices=[("success", "成功"), ("failed", "失败")])
    synced_at = models.DateTimeField(auto_now_add=True)
    message = models.TextField(blank=True)

    class Meta:
        ordering = ["-synced_at"]


class DailyWeatherStat(models.Model):
    date = models.DateField(unique=True)
    temperature_avg = models.DecimalField(max_digits=6, decimal_places=2)
    temperature_peak = models.DecimalField(max_digits=6, decimal_places=1)
    humidity_avg = models.DecimalField(max_digits=6, decimal_places=2)
    humidity_peak = models.DecimalField(max_digits=6, decimal_places=1)
    pm25_avg = models.DecimalField(max_digits=6, decimal_places=2)
    pm25_peak = models.DecimalField(max_digits=6, decimal_places=1)
    illumination_avg = models.DecimalField(max_digits=10, decimal_places=2)
    illumination_peak = models.DecimalField(max_digits=10, decimal_places=1)
    risk_warning = models.CharField(max_length=200, default="正常")

    class Meta:
        ordering = ["date"]


class HourlyWeatherProfile(models.Model):
    hour = models.IntegerField(unique=True)
    sample_count = models.IntegerField()
    temperature_avg = models.DecimalField(max_digits=6, decimal_places=2)
    humidity_avg = models.DecimalField(max_digits=6, decimal_places=2)
    pm25_avg = models.DecimalField(max_digits=6, decimal_places=2)
    illumination_avg = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["hour"]


class DailyComfortStat(models.Model):
    date = models.DateField(unique=True)
    sample_count = models.IntegerField()
    comfort_index_avg = models.DecimalField(max_digits=6, decimal_places=2)
    comfortable_count = models.IntegerField()
    attention_count = models.IntegerField()
    uncomfortable_count = models.IntegerField()
    comfort_rate = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        ordering = ["date"]


class DailyRiskStat(models.Model):
    date = models.DateField(unique=True)
    sample_count = models.IntegerField()
    high_temp_count = models.IntegerField()
    high_humidity_count = models.IntegerField()
    pollution_count = models.IntegerField()
    fire_risk_count = models.IntegerField()
    normal_count = models.IntegerField()
    risk_rate = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        ordering = ["date"]


class TopRiskDay(models.Model):
    rank = models.IntegerField(unique=True)
    date = models.DateField()
    risk_score = models.DecimalField(max_digits=8, decimal_places=2)
    dangerous_count = models.IntegerField()
    temperature_peak = models.DecimalField(max_digits=6, decimal_places=1)
    humidity_low = models.DecimalField(max_digits=6, decimal_places=1)
    pm25_peak = models.DecimalField(max_digits=6, decimal_places=1)
    illumination_peak = models.DecimalField(max_digits=10, decimal_places=1)

    class Meta:
        ordering = ["rank"]