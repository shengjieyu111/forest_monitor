from django.db import models


class VisitorRecord(models.Model):
    GATE_CHOICES = [
        ("东门", "东门"),
        ("西门", "西门"),
        ("南门", "南门"),
        ("北门", "北门"),
    ]

    TICKET_TYPE_CHOICES = [
        ("成人票", "成人票"),
        ("学生票", "学生票"),
        ("团体票", "团体票"),
        ("老人票", "老人票"),
    ]

    visit_time = models.DateTimeField("记录时间")
    gate = models.CharField("入口", max_length=20, choices=GATE_CHOICES)
    visitor_count = models.IntegerField("游客数量")
    ticket_type = models.CharField("票种", max_length=20, choices=TICKET_TYPE_CHOICES)
    weather = models.CharField("天气", max_length=30, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "visitor_record"
        ordering = ["-visit_time", "-id"]
        verbose_name = "游客原始记录"
        verbose_name_plural = "游客原始记录"
        indexes = [
            models.Index(fields=["visit_time"], name="visitor_rec_visit_t_033860_idx"),
            models.Index(fields=["gate", "visit_time"], name="visitor_rec_gate_73efc5_idx"),
        ]

    def __str__(self):
        return f"{self.visit_time:%Y-%m-%d %H:%M} {self.gate} {self.visitor_count}人"


class VisitorDailyStat(models.Model):
    stat_date = models.DateField("统计日期")
    total_count = models.IntegerField("当日游客总量")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "visitor_daily_stat"
        ordering = ["stat_date"]
        verbose_name = "每日游客统计"
        verbose_name_plural = "每日游客统计"
        indexes = [
            models.Index(fields=["stat_date"], name="visitor_dai_stat_da_5c39c2_idx"),
        ]

    def __str__(self):
        return f"{self.stat_date:%Y-%m-%d} {self.total_count}人"


class VisitorHourlyStat(models.Model):
    hour = models.IntegerField("小时")
    total_count = models.IntegerField("该小时累计游客数量")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "visitor_hourly_stat"
        ordering = ["hour"]
        verbose_name = "小时游客统计"
        verbose_name_plural = "小时游客统计"
        indexes = [
            models.Index(fields=["hour"], name="visitor_hou_hour_c9e4d7_idx"),
        ]

    def __str__(self):
        return f"{self.hour}:00 {self.total_count}人"


class VisitorGateStat(models.Model):
    gate = models.CharField("入口名称", max_length=20)
    total_count = models.IntegerField("该入口累计游客数量")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "visitor_gate_stat"
        ordering = ["-total_count"]
        verbose_name = "入口游客统计"
        verbose_name_plural = "入口游客统计"
        indexes = [
            models.Index(fields=["gate"], name="visitor_gat_gate_53a612_idx"),
        ]

    def __str__(self):
        return f"{self.gate} {self.total_count}人"
