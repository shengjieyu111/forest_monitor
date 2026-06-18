import csv
import random
from datetime import datetime, timedelta
from pathlib import Path


START_DATE = datetime(2024, 1, 1)
# 历史总数据只生成到运行当天的前一天，今天的数据由
# generate_today_visitor_data.py 单独生成并通过 HDFS 管理页面追加。
END_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
START_MINUTE = 8 * 60
END_MINUTE = 18 * 60 + 55
INTERVAL_MINUTES = 5
OUTPUT_PATH = Path("datasets") / "visitor_records.csv"

GATE_FACTORS = {
    "东门": 1.5,
    "南门": 1.0,
    "西门": 0.7,
}

WEATHER_FACTORS = {
    "晴": 1.2,
    "多云": 1.0,
    "阴": 0.85,
    "小雨": 0.6,
}

HOUR_FACTORS = {
    8: 0.4,
    9: 0.7,
    10: 1.2,
    11: 1.5,
    12: 1.0,
    13: 0.6,
    14: 1.2,
    15: 1.6,
    16: 1.3,
    17: 0.6,
    18: 0.3,
}

WEATHER_WEIGHTS = {
    "晴": 0.42,
    "多云": 0.32,
    "阴": 0.18,
    "小雨": 0.08,
}

HOLIDAY_RANGES = [
    (datetime(2024, 5, 1).date(), datetime(2024, 5, 5).date()),
    (datetime(2024, 10, 1).date(), datetime(2024, 10, 7).date()),
    (datetime(2025, 5, 1).date(), datetime(2025, 5, 5).date()),
    (datetime(2025, 10, 1).date(), datetime(2025, 10, 7).date()),
    (datetime(2026, 5, 1).date(), datetime(2026, 5, 5).date()),
]

FIELDNAMES = [
    "record_id",
    "visit_time",
    "gate",
    "visitor_count",
    "weather",
    "ticket_type",
]


def is_holiday(current_date):
    return any(start <= current_date <= end for start, end in HOLIDAY_RANGES)


def get_calendar_factor(current_date):
    if is_holiday(current_date):
        return 1.8
    if current_date.weekday() >= 5:
        return 1.4
    return 1.0


def get_season_factor(month):
    if month in (3, 4, 5):
        return 1.2
    if month in (6, 7, 8):
        return 1.4
    if month in (9, 10, 11):
        return 1.3
    return 0.8


def choose_daily_weather():
    weather_names = list(WEATHER_WEIGHTS)
    weather_weights = list(WEATHER_WEIGHTS.values())
    return random.choices(weather_names, weights=weather_weights, k=1)[0]


def get_base_visitor_count(hour):
    if 10 <= hour <= 12 or 14 <= hour <= 16:
        return random.randint(10, 25)
    if hour == 13:
        return random.randint(4, 12)
    if 8 <= hour <= 9 or 17 <= hour <= 18:
        return random.randint(1, 8)
    return random.randint(5, 15)


def choose_ticket_type(current_date):
    holiday = is_holiday(current_date)
    weekend = current_date.weekday() >= 5

    if holiday:
        weights = [0.42, 0.20, 0.38]
    elif weekend:
        weights = [0.50, 0.25, 0.25]
    else:
        weights = [0.66, 0.25, 0.09]

    return random.choices(
        ["成人票", "学生票", "团体票"],
        weights=weights,
        k=1,
    )[0]


def calculate_visitor_count(visit_time, gate, weather):
    base_count = get_base_visitor_count(visit_time.hour)
    calendar_factor = get_calendar_factor(visit_time.date())
    season_factor = get_season_factor(visit_time.month)
    gate_factor = GATE_FACTORS[gate]
    weather_factor = WEATHER_FACTORS[weather]
    hour_factor = HOUR_FACTORS[visit_time.hour]

    expected_count = (
        base_count
        * gate_factor
        * hour_factor
        * calendar_factor
        * season_factor
        * weather_factor
    )

    # Small proportional noise prevents repeated values without hiding larger trends.
    random_noise = random.gauss(0, max(0.8, expected_count * 0.08))
    return max(0, int(round(expected_count + random_noise)))


def generate_rows():
    record_id = 1
    current_date = START_DATE

    while current_date <= END_DATE:
        weather = choose_daily_weather()
        date_value = current_date.date()

        for minute_of_day in range(START_MINUTE, END_MINUTE + 1, INTERVAL_MINUTES):
            hour = minute_of_day // 60
            minute = minute_of_day % 60
            visit_time = current_date.replace(hour=hour, minute=minute, second=0)

            for gate in GATE_FACTORS:
                yield {
                    "record_id": record_id,
                    "visit_time": visit_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "gate": gate,
                    "visitor_count": calculate_visitor_count(visit_time, gate, weather),
                    "weather": weather,
                    "ticket_type": choose_ticket_type(date_value),
                }
                record_id += 1

        current_date += timedelta(days=1)


def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    total_records = 0
    total_visitors = 0
    gate_totals = {gate: 0 for gate in GATE_FACTORS}

    try:
        with OUTPUT_PATH.open("w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
            writer.writeheader()

            for row in generate_rows():
                writer.writerow(row)
                total_records += 1
                total_visitors += row["visitor_count"]
                gate_totals[row["gate"]] += row["visitor_count"]
    except PermissionError:
        print("写入失败：datasets/visitor_records.csv 可能正在被 Excel、WPS 或其他程序打开。")
        print("请关闭该文件后重新运行：python scripts/generate_visitor_data.py")
        raise

    print(f"游客模拟数据生成完成：{OUTPUT_PATH.as_posix()}")
    print(f"共生成 {total_records} 条数据")
    print(f"总游客量：{total_visitors}")
    for gate, total in gate_totals.items():
        print(f"{gate}游客量：{total}")


if __name__ == "__main__":
    main()
