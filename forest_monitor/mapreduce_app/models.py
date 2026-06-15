from django.db import models


class MapReduceSyncLog(models.Model):
    job_type = models.CharField(max_length=32)
    source_path = models.CharField(max_length=255)
    record_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, default='success')
    message = models.TextField(blank=True)
    synced_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-synced_at']

    def __str__(self):
        return f'{self.job_type} - {self.synced_at:%Y-%m-%d %H:%M:%S}'


class DailyWeatherStat(models.Model):
    date = models.DateField(unique=True)
    temperature_avg = models.FloatField()
    temperature_peak = models.FloatField()
    humidity_avg = models.FloatField()
    humidity_peak = models.FloatField()
    pm25_avg = models.FloatField()
    pm25_peak = models.FloatField()
    illumination_avg = models.FloatField()
    illumination_peak = models.FloatField()
    risk_warning = models.CharField(max_length=255, default='正常')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f'{self.date} 每日综合统计'


class HourlyWeatherProfile(models.Model):
    hour = models.PositiveSmallIntegerField(unique=True)
    sample_count = models.PositiveIntegerField()
    temperature_avg = models.FloatField()
    humidity_avg = models.FloatField()
    pm25_avg = models.FloatField()
    illumination_avg = models.FloatField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['hour']

    def __str__(self):
        return f'{self.hour:02d}:00 小时画像'


class DailyRiskStat(models.Model):
    date = models.DateField(unique=True)
    sample_count = models.PositiveIntegerField()
    high_temp_count = models.PositiveIntegerField()
    high_humidity_count = models.PositiveIntegerField()
    pollution_count = models.PositiveIntegerField()
    fire_risk_count = models.PositiveIntegerField()
    normal_count = models.PositiveIntegerField()
    risk_rate = models.FloatField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f'{self.date} 风险统计'


class DailyComfortStat(models.Model):
    date = models.DateField(unique=True)
    sample_count = models.PositiveIntegerField()
    comfort_index_avg = models.FloatField()
    comfortable_count = models.PositiveIntegerField()
    attention_count = models.PositiveIntegerField()
    uncomfortable_count = models.PositiveIntegerField()
    comfort_rate = models.FloatField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f'{self.date} 舒适度统计'


class TopRiskDay(models.Model):
    rank = models.PositiveSmallIntegerField(unique=True)
    date = models.DateField()
    risk_score = models.FloatField()
    dangerous_count = models.PositiveIntegerField()
    temperature_peak = models.FloatField()
    humidity_low = models.FloatField()
    pm25_peak = models.FloatField()
    illumination_peak = models.FloatField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['rank']

    def __str__(self):
        return f'Top {self.rank} - {self.date}'
