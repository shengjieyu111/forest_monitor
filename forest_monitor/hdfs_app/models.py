from django.db import models


class MapReduceRun(models.Model):
    STATUS_CHOICES = [
        ('queued', '排队中'),
        ('running', '运行中'),
        ('success', '成功'),
        ('failed', '失败'),
    ]

    input_path = models.CharField(max_length=255, default='/waether/input')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='queued')
    auto_refresh = models.BooleanField(default=True)
    message = models.CharField(max_length=255, blank=True)
    output_log = models.TextField(blank=True)
    process_id = models.PositiveIntegerField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'#{self.pk} {self.status}'
