from datetime import datetime, timedelta
import random

from django.core.management.base import BaseCommand
from django.utils import timezone

from visitor.models import VisitorRecord


class Command(BaseCommand):
    help = "生成游客流量演示数据"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=14)

    def handle(self, *args, **options):
        days = max(1, options["days"])
        gates = [choice[0] for choice in VisitorRecord.GATE_CHOICES]
        ticket_types = [choice[0] for choice in VisitorRecord.TICKET_TYPE_CHOICES]
        weather_options = ["晴", "多云", "小雨", "阴"]
        today = timezone.localdate()
        created = 0

        for offset in range(days):
            day = today - timedelta(days=offset)
            for hour in range(8, 19):
                base = 45
                if 10 <= hour <= 11:
                    base = 120
                elif 14 <= hour <= 16:
                    base = 150
                elif hour >= 17:
                    base = 80

                naive_time = datetime.combine(day, datetime.min.time()).replace(hour=hour)
                visit_time = timezone.make_aware(naive_time)
                VisitorRecord.objects.create(
                    visit_time=visit_time,
                    gate=random.choice(gates),
                    visitor_count=max(8, base + random.randint(-25, 35)),
                    ticket_type=random.choice(ticket_types),
                    weather=random.choice(weather_options),
                )
                created += 1

        self.stdout.write(self.style.SUCCESS(f"已生成 {created} 条游客流量记录。"))
