import pymysql
import csv
from datetime import datetime

# =====================
# 将devices模块的3个原始表加载入数据库
# =====================
conn = pymysql.connect(
    host="localhost",
    user="root",
    password="123456",
    database="monitor_db",
    charset="utf8mb4"
)

cursor = conn.cursor()

# =====================
# Step 0: 读取 device_id -> id 映射（关键优化）
# =====================
device_map = {}

cursor.execute("SELECT id, device_id FROM devices_device")
for db_id, device_id in cursor.fetchall():
    device_map[device_id] = db_id

print(f"已加载设备映射: {len(device_map)} 条")


# =====================
# Step 1: 设备表（幂等：存在则更新）
# =====================
with open("device_info.csv", "r", encoding="utf-8") as f:
    reader = csv.reader(f)

    for row in reader:
        device_id, name, dtype, sub_type, lon, lat, location, install_date, status = row
        now = datetime.now()

        if device_id in device_map:
            # ===== 更新 =====
            sql = """
            UPDATE devices_device
            SET device_name=%s,
                device_type=%s,
                sub_type=%s,
                longitude=%s,
                latitude=%s,
                location=%s,
                install_date=%s,
                status=%s,
                updated_at=%s
            WHERE device_id=%s
            """
            cursor.execute(sql, (
                name, dtype, sub_type,
                float(lon), float(lat), location,
                install_date, status,
                now, device_id
            ))

        else:
            # ===== 插入 =====
            sql = """
            INSERT INTO devices_device
            (device_id, device_name, device_type, sub_type,
             longitude, latitude, location, install_date,
             status, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """
            cursor.execute(sql, (
                device_id, name, dtype, sub_type,
                float(lon), float(lat), location,
                install_date, status,
                now, now
            ))

            device_map[device_id] = cursor.lastrowid

conn.commit()
print("devices_device 导入完成（幂等）")


# =====================
# Step 2: work log（防重复：device_id + record_time）
# =====================
with open("device_work_log.csv", "r", encoding="utf-8") as f:
    reader = csv.reader(f)

    for row in reader:
        device_id, cpu, mem, temp, power, net, uptime, record_time = row

        db_id = device_map.get(device_id)
        if not db_id:
            continue

        # 判断是否已存在
        cursor.execute("""
            SELECT 1 FROM devices_deviceworklog
            WHERE device_id=%s AND record_time=%s
            LIMIT 1
        """, (db_id, record_time))

        if cursor.fetchone():
            continue

        sql = """
        INSERT INTO devices_deviceworklog
        (cpu_usage, memory_usage, temperature, power,
         network_delay, uptime, record_time, device_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """

        cursor.execute(sql, (
            float(cpu),
            float(mem),
            float(temp),
            float(power),
            float(net),
            float(uptime),
            record_time,
            db_id
        ))

conn.commit()
print("devices_deviceworklog 导入完成（幂等）")


# =====================
# Step 3: fault log（防重复：device_id + record_time + type）
# =====================
with open("device_fault_log.csv", "r", encoding="utf-8") as f:
    reader = csv.reader(f)

    for row in reader:
        _, device_id, fault_type, level, is_resolved, record_time = row

        db_id = device_map.get(device_id)
        if not db_id:
            continue

        # 去重判断
        cursor.execute("""
            SELECT 1 FROM devices_devicefault
            WHERE device_id=%s AND record_time=%s AND fault_type=%s
            LIMIT 1
        """, (db_id, record_time, fault_type))

        if cursor.fetchone():
            continue

        sql = """
        INSERT INTO devices_devicefault
        (fault_type, fault_level, is_resolved, record_time, device_id)
        VALUES (%s,%s,%s,%s,%s)
        """

        cursor.execute(sql, (
            fault_type,
            int(level),
            int(is_resolved),
            record_time,
            db_id
        ))

conn.commit()
print("devices_devicefault 导入完成（幂等）")


cursor.close()
conn.close()

print("全部数据导入完成 ✅（可重复执行无错误）")