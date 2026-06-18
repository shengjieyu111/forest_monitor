from datetime import datetime, timedelta
import random
import csv
import os

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "生成设备CSV模拟数据（用于Hadoop MR）"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--devices", type=int, default=20)
        parser.add_argument("--output", type=str, default="data")

    def handle(self, *args, **options):
        days = options["days"]
        device_count = options["devices"]
        output_dir = options["output"]

        os.makedirs(output_dir, exist_ok=True)

        today = timezone.localdate()

        work_path = os.path.join(output_dir, "device_work_log.csv")
        fault_path = os.path.join(output_dir, "device_fault_log.csv")

        with open(work_path, "w", newline="", encoding="utf-8") as work_file, \
             open(fault_path, "w", newline="", encoding="utf-8") as fault_file:

            work_writer = csv.writer(work_file)
            fault_writer = csv.writer(fault_file)

            # headers
            work_writer.writerow([
                "device_id", "cpu", "memory", "temperature",
                "power", "network_delay", "uptime", "record_time"
            ])

            fault_writer.writerow([
                "id", "device_id", "fault_type", "fault_level",
                "is_resolved", "record_time"
            ])

            fault_types = ["NETWORK", "POWER", "SENSOR", "OVERHEAT", "CPU_SPIKE"]

            work_count = 0
            fault_count = 0

            for i in range(device_count):
                device_id = f"D{i:04d}"

                for d in range(days):
                    day = today - timedelta(days=d)

                    for hour in range(0, 24, 2):

                        ts = datetime.combine(day, datetime.min.time()).replace(hour=hour)

                        cpu = random.uniform(10, 90)
                        mem = random.uniform(20, 80)
                        temp = random.uniform(30, 90)
                        power = random.uniform(10, 60)
                        net = random.uniform(5, 100)
                        uptime = random.uniform(60, 100)

                        work_writer.writerow([
                            device_id, cpu, mem, temp,
                            power, net, uptime,
                            ts.strftime("%Y-%m-%d %H:%M:%S")
                        ])

                        work_count += 1

                        # 故障生成
                        if random.random() < 0.12:
                            fault_writer.writerow([
                                fault_count,
                                device_id,
                                random.choice(fault_types),
                                random.randint(1, 5),
                                random.choice([0, 1]),
                                ts.strftime("%Y-%m-%d %H:%M:%S")
                            ])
                            fault_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"CSV生成完成：work={work_count}, fault={fault_count}"
            )
        )