import argparse
import csv
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "datasets"

FIELDNAMES = [
    "record_id",
    "visit_time",
    "gate",
    "visitor_count",
    "weather",
    "ticket_type",
]

GATE_FACTORS = {
    "东门": 1.5,
    "南门": 1.0,
    "西门": 0.7,
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

WEATHER_FACTORS = {
    "晴": 1.2,
    "多云": 1.0,
    "阴": 0.85,
    "小雨": 0.6,
}

SEASON_FACTORS = {
    1: 0.8,
    2: 0.8,
    3: 1.2,
    4: 1.2,
    5: 1.2,
    6: 1.4,
    7: 1.4,
    8: 1.4,
    9: 1.3,
    10: 1.3,
    11: 1.3,
    12: 0.8,
}


def choose_weather():
    return random.choices(
        list(WEATHER_FACTORS),
        weights=[0.45, 0.30, 0.18, 0.07],
        k=1,
    )[0]


def choose_ticket_type(is_weekend):
    ticket_types = ["成人票", "学生票", "团体票"]
    weights = [0.50, 0.20, 0.30] if is_weekend else [0.65, 0.25, 0.10]
    return random.choices(ticket_types, weights=weights, k=1)[0]


def get_base_count(hour):
    if 10 <= hour <= 12 or 14 <= hour <= 16:
        return random.randint(10, 25)
    if hour == 13:
        return random.randint(4, 12)
    if 8 <= hour <= 9 or 17 <= hour <= 18:
        return random.randint(1, 8)
    return random.randint(5, 15)


def generate_count(current_date, current_time, gate, weather):
    hour = current_time.hour
    day_factor = 1.4 if current_date.weekday() >= 5 else 1.0
    expected_count = (
        get_base_count(hour)
        * HOUR_FACTORS[hour]
        * GATE_FACTORS[gate]
        * WEATHER_FACTORS[weather]
        * SEASON_FACTORS[current_date.month]
        * day_factor
    )
    noise = random.gauss(0, max(0.8, expected_count * 0.08))
    return max(0, int(round(expected_count + noise)))


def generate_today_data(target_date=None):
    target_date = target_date or date.today()
    output_path = OUTPUT_DIR / f"visitor_today_{target_date:%Y-%m-%d}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    record_id = 1
    total_count = 0
    gate_totals = {gate: 0 for gate in GATE_FACTORS}
    current_dt = datetime.combine(target_date, time(8, 0))
    end_dt = datetime.combine(target_date, time(18, 55))
    is_weekend = target_date.weekday() >= 5
    daily_weather = choose_weather()

    with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()

        while current_dt <= end_dt:
            for gate in GATE_FACTORS:
                visitor_count = generate_count(
                    target_date,
                    current_dt.time(),
                    gate,
                    daily_weather,
                )
                writer.writerow(
                    {
                        "record_id": record_id,
                        "visit_time": current_dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "gate": gate,
                        "visitor_count": visitor_count,
                        "weather": daily_weather,
                        "ticket_type": choose_ticket_type(is_weekend),
                    }
                )
                record_id += 1
                total_count += visitor_count
                gate_totals[gate] += visitor_count

            current_dt += timedelta(minutes=5)

    total_records = record_id - 1
    print(f"当天游客数据生成完成：{output_path}")
    print(f"日期：{target_date}")
    print(f"天气：{daily_weather}")
    print(f"记录数：{total_records} 条")
    print(f"游客总数：{total_count} 人")
    print("各入口游客量：")
    for gate, count in gate_totals.items():
        print(f"  {gate}：{count} 人")

    return output_path


def parse_args():
    parser = argparse.ArgumentParser(description="生成指定日期的游客模拟数据 CSV")
    parser.add_argument(
        "--date",
        dest="target_date",
        type=lambda value: datetime.strptime(value, "%Y-%m-%d").date(),
        help="生成日期，格式为 YYYY-MM-DD；不填写时使用当天日期",
    )
    return parser.parse_args()


if __name__ == "__main__":
    try:
        args = parse_args()
        generate_today_data(args.target_date)
    except PermissionError:
        print("生成失败：对应日期的 visitor_today_YYYY-MM-DD.csv 正被其他程序占用。")
        print("请关闭该文件后重新运行：python scripts/generate_today_visitor_data.py")
