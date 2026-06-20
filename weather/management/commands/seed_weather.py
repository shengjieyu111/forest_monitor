from datetime import datetime, timedelta
import random
import csv
from pathlib import Path

from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "生成气象CSV演示数据（weather_15days.csv）约5万条"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=15)
        parser.add_argument("--devices", type=int, default=23)
        parser.add_argument("--output", type=str, default="")

    def handle(self, *args, **options):
        days = max(1, options["days"])
        device_count = max(1, options["devices"])
        output_path = options["output"]

        if not output_path:
            output_path = str(Path(settings.BASE_DIR) / "datasets" / "weather_15days.csv")

        city = "北京鹫峰国家森林公园"
        today = datetime.now().date()
        created = 0

        # 设备偏差配置（模拟多台设备同时采集）
        devices = []
        for i in range(device_count):
            devices.append({
                "temp_offset": random.uniform(-1.5, 1.5),
                "humidity_offset": random.uniform(-3, 3),
                "pm25_offset": random.uniform(-5, 5),
            })

        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            # 不写表头，MR代码会跳过表头行

            for day_offset in range(days):
                date = today - timedelta(days=day_offset)
                date_str = date.isoformat()

                day_temp_offset = random.uniform(-12, 18)
                day_humidity_offset = random.uniform(-20, 25)
                day_pm25_offset = random.uniform(-15, 30)

                for hour in range(24):
                    # 每10分钟一条记录
                    for minute in [0, 10, 20, 30, 40, 50]:
                        time_str = f"{hour:02d}:{minute:02d}"

                        # 基础气象值（所有设备共享当日当时的大环境）
                        base_temp = 22 + day_temp_offset + random.uniform(-2, 8)
                        if 14 <= hour <= 16:
                            base_temp += 8
                        elif 0 <= hour <= 6:
                            base_temp -= 6

                        base_humidity = 70 + day_humidity_offset + random.uniform(-8, 12)
                        base_pm25 = 40 + day_pm25_offset + random.uniform(-8, 15)

                        illumination_base = 0
                        if 6 <= hour <= 18:
                            illumination_base = 15000 + (hour - 6) * 5000
                            if hour >= 12:
                                illumination_base = 90000 - (hour - 12) * 5000

                        # 每台设备记录一条数据（模拟多台设备同时采集）
                        for device in devices:
                            temperature = round(base_temp + device["temp_offset"] + random.uniform(-0.5, 0.5), 1)
                            humidity = round(base_humidity + device["humidity_offset"] + random.uniform(-1, 1), 1)
                            humidity = max(30, min(98, humidity))
                            pm25 = round(base_pm25 + device["pm25_offset"] + random.uniform(-2, 2), 1)
                            pm25 = max(10, min(150, pm25))
                            illumination = round(illumination_base * (0.7 + random.uniform(0, 0.6)), 1)

                            # 7字段格式：city,date,hour,temperature,humidity,pm25,illumination
                            writer.writerow([
                                city,
                                date_str,
                                time_str,
                                temperature,
                                humidity,
                                pm25,
                                illumination,
                            ])
                            created += 1

        self.stdout.write(self.style.SUCCESS(
            f"已生成 {created} 条气象数据到 {output_path}（{device_count}台设备 × {days}天 × 144条/天）"
        ))