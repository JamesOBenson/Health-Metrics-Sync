#!/usr/bin/env python3
"""Create Garmin-compatible CSV for manual upload."""

import csv
import json
from datetime import datetime


def convert_to_garmin_csv(json_file, output_csv):
    """Convert JSON records to Garmin CSV format."""

    with open(json_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    records.sort(key=lambda x: x.get("date", "") + x.get("time", ""))

    rows = []
    for rec in records:
        try:
            dt = datetime.fromisoformat(
                rec.get("date", "") + " " + rec.get("time", "")
            )
            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M:%S")
        except Exception:
            continue

        weight = rec.get("weight", "")
        bmi = rec.get("bmi", "")
        fat = rec.get("percent_fat", "")

        rows.append(
            {
                "weight": weight,
                "bmi": bmi,
                "fat": fat,
                "date": date_str,
                "time": time_str,
            }
        )

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Body"])
        writer.writerow(["weight", "bmi", "fat", "date", "time"])
        for row in rows:
            writer.writerow(
                [
                    row["weight"],
                    row["bmi"],
                    row["fat"],
                    row["date"],
                    row["time"],
                ]
            )

    return len(rows)


if __name__ == "__main__":
    json_file = "garmin_body_composition.json"
    output_csv = "garmin_upload.csv"

    try:
        count = convert_to_garmin_csv(json_file, output_csv)
        print(f"✓ Created {output_csv} with {count} records")
        print(f"\nUpload to: https://connect.garmin.com/modern/import-data")
        print(f"\nCSV format:")
        print("  Body")
        print("  weight,bmi,fat,date,time")

        with open(output_csv, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            next(reader)
            for row in reader:
                print(f"  {row[0]},{row[1]},{row[2]},{row[3]},{row[4]}")
                break
    except FileNotFoundError:
        print(f"❌ {json_file} not found")
        print("Run oxiline_to_garmin.py first to generate the JSON file")