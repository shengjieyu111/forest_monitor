from datetime import datetime, timedelta
import random

from django.core.management.base import BaseCommand
from django.utils import timezone

from devices.devices_geo import generate_location_point
from devices.models import Device, DeviceWorkLog, DeviceFault


class Command(BaseCommand):
    help = "生成设备模拟数据（Device / WorkLog / FaultLog）"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--devices", type=int, default=20)

    def handle(self, *args, **options):
        days = max(1, options["days"])
        device_count = options["devices"]

        device_types = ["camera", "sensor"]
        statuses = ["ONLINE", "FAULT", "MAINTENANCE"]
        locations = [
            "CORE_SCENIC",
            "FIRE_ZONE",
            "ENTRANCE_GATE",
            "INFRA_AREA",
            "TRAIL_ZONE"
        ]

        fault_types = [
            "NETWORK",
            "POWER",
            "SENSOR_ERROR",
            "OVERHEAT",
            "CPU_SPIKE"
        ]

        today = timezone.localdate()

        # =========================
        # 1. 创建设备
        # =========================
        devices = []

        for i in range(device_count):
            location = random.choice(locations)
            longitude, latitude = generate_location_point(location, seed=f"seed:{i}:{location}")
            device = Device.objects.create(
                device_id=f"D{i:04d}",
                device_name=f"Device_{i}",
                device_type=random.choice(device_types),
                sub_type="v1",

                longitude=longitude,
                latitude=latitude,

                location=location,
                install_date=today - timedelta(days=random.randint(30, 365)),
                status=random.choice(statuses),
            )
            devices.append(device)

        # =========================
        # 2. 生成 WorkLog + FaultLog
        # =========================
        work_created = 0
        fault_created = 0

        for offset in range(days):
            day = today - timedelta(days=offset)

            for device in devices:
                for hour in range(0, 24, 2):

                    ts = datetime.combine(day, datetime.min.time()).replace(hour=hour)
                    ts = timezone.make_aware(ts)

                    DeviceWorkLog.objects.create(
                        device=device,
                        cpu_usage=random.uniform(10, 90),
                        memory_usage=random.uniform(20, 80),
                        temperature=random.uniform(30, 90),
                        power=random.uniform(10, 60),
                        network_delay=random.uniform(5, 100),
                        uptime=random.uniform(60, 100),
                        record_time=ts
                    )

                    work_created += 1

                    # =========================
                    # 3. 故障模拟
                    # =========================
                    if random.random() < 0.15:
                        DeviceFault.objects.create(
                            device=device,
                            fault_type=random.choice(fault_types),
                            fault_level=random.randint(1, 5),
                            is_resolved=random.choice([True, False]),
                            record_time=ts
                        )
                        fault_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"生成完成：设备={device_count}，日志={work_created}，故障={fault_created}"
            )
        )
