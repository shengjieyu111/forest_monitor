from datetime import datetime, timedelta
import random
import csv

from django.core.management.base import BaseCommand
from django.utils import timezone

from devices.models import Device


class Command(BaseCommand):
    help = "生成设备CSV数据（devices_info / work_log / fault_log）"

    def handle(self, *args, **options):

        # =========================
        # 时间范围
        # =========================
        today = timezone.localdate()

        work_days = 30          # 工作日志：1个月
        fault_days = 90         # 故障日志：3个月（4/5/6月）

        # =========================
        # 故障类型（扩展版）
        # =========================
        fault_types = [
            "LENS_DIRTY",
            "SENSOR_ERROR",
            "NETWORK_OFFLINE",
            "OVERHEAT",
            "POWER_FAILURE",
            "CPU_SPIKE",
            "STORAGE_FULL",
            "IMAGE_BLUR",
            "SIGNAL_WEAK"
        ]

        # =========================
        # 区域故障权重（越高越容易出问题）
        # =========================
        location_risk = {
            "FIRE_ZONE": 0.35,
            "INFRA_AREA": 0.25,
            "TRAIL_ZONE": 0.20,
            "ENTRANCE_GATE": 0.15,
            "CORE_SCENIC": 0.10
        }

        # =========================
        # 设备类型故障偏好
        # =========================
        device_fault_bias = {
            "FIRE_CAMERA": ["LENS_DIRTY", "OVERHEAT", "CPU_SPIKE"],
            "NORMAL_CAMERA": ["IMAGE_BLUR", "LENS_DIRTY", "NETWORK_OFFLINE"],
            "FLOW_SENSOR": ["SENSOR_ERROR", "NETWORK_OFFLINE"],
            "METEO_SENSOR": ["SENSOR_ERROR", "SIGNAL_WEAK"]
        }

        # =========================
        # 1. 读取设备
        # =========================
        devices = list(Device.objects.all()[:120])

        # =========================
        # CSV文件
        # =========================
        info_file = open("devices_info.csv", "w", newline="", encoding="utf-8")
        work_file = open("devices_work_log(1.5w).csv", "w", newline="", encoding="utf-8")
        fault_file = open("devices_fault_log.csv", "w", newline="", encoding="utf-8")

        info_writer = csv.writer(info_file)
        work_writer = csv.writer(work_file)
        fault_writer = csv.writer(fault_file)

        # =========================
        # 2. devices_info
        # =========================
        for d in devices:
            info_writer.writerow([
                d.device_id,
                d.device_name,
                d.device_type,
                d.sub_type,
                d.longitude,
                d.latitude,
                d.location,
                d.install_date,
                d.status
            ])

        # =========================
        # 3. WORK LOG（1个月，目标15000）
        # =========================
        work_id = 1
        work_target = 15000

        for i in range(work_target):
            device = random.choice(devices)

            day_offset = random.randint(0, work_days - 1)
            hour = random.randint(0, 23)

            ts = datetime.combine(today - timedelta(days=day_offset),
                                  datetime.min.time()).replace(hour=hour)
            ts = timezone.make_aware(ts)

            work_writer.writerow([
                work_id,
                device.device_id,
                round(random.uniform(5, 95), 2),
                round(random.uniform(10, 90), 2),
                round(random.uniform(25, 95), 2),
                round(random.uniform(10, 80), 2),
                round(random.uniform(1, 120), 2),
                round(random.uniform(60, 100), 2),
                ts
            ])

            work_id += 1

        # =========================
        # 4. FAULT LOG（3个月，目标15000）
        # =========================
        fault_id = 1
        fault_target = 15000

        for i in range(fault_target):

            device = random.choice(devices)

            # 时间（4~6月分布）
            day_offset = random.randint(0, fault_days - 1)
            hour = random.randint(0, 23)

            ts = datetime.combine(today - timedelta(days=day_offset),
                                  datetime.min.time()).replace(hour=hour)
            ts = timezone.make_aware(ts)

            # 设备类型（从名称解析）
            if "FIRE_CAMERA" in device.sub_type or "FIRE_CAMERA" in device.device_name:
                dev_type = "FIRE_CAMERA"
            elif "FLOW_SENSOR" in device.device_name:
                dev_type = "FLOW_SENSOR"
            elif "METEO_SENSOR" in device.device_name:
                dev_type = "METEO_SENSOR"
            else:
                dev_type = "NORMAL_CAMERA"

            # =========================
            # 故障类型（加权逻辑）
            # =========================
            bias_pool = device_fault_bias.get(dev_type, fault_types)

            # 区域风险影响概率
            risk = location_risk.get(device.location, 0.1)

            if random.random() < risk:
                fault_type = random.choice(bias_pool)
            else:
                fault_type = random.choice(fault_types)

            fault_writer.writerow([
                fault_id,
                device.device_id,
                fault_type,
                random.randint(1, 5),
                random.randint(0, 1),
                ts
            ])

            fault_id += 1

        # =========================
        # close
        # =========================
        info_file.close()
        work_file.close()
        fault_file.close()

        self.stdout.write(self.style.SUCCESS(
            f"完成：devices=120, work=15000, fault=15000"
        ))