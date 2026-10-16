#!/usr/bin/env python3
"""Convert Oxiline Scale CSV to Garmin Connect format and upload."""

import csv
import json
from datetime import datetime
import sys
import re
import getpass
import time


def parse_oxiline_csv(csv_path: str):
    """Parse CSV, grouping metrics by measurement session (5 min window)."""
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        return []

    def is_valid_timestamp(ts):
        return bool(re.match(r"\d{4}-\d{2}-\d{2}", ts))

    def parse_timestamp(ts):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None

    measurements = []
    current_ts = None
    current_metrics = {}

    for row in rows:
        ts = row.get("Time", row.get("timestamp", ""))
        metric = row.get("Metric", row.get("metric", ""))
        value = row.get("Value", row.get("value", ""))

        if not metric or not value:
            continue

        if is_valid_timestamp(ts):
            if current_ts and current_metrics:
                measurements.append({"timestamp": current_ts, "metrics": current_metrics})
            dt = parse_timestamp(ts)
            if dt:
                current_ts = ts
                current_metrics = {metric: value}
            else:
                current_ts = None
                current_metrics = {}
        elif current_ts:
            current_metrics[metric] = value

    if current_ts and current_metrics:
        measurements.append({"timestamp": current_ts, "metrics": current_metrics})

    if not measurements:
        return []

    windowed = []
    current_group = {"timestamp": measurements[0]["timestamp"], "metrics": measurements[0]["metrics"].copy()}

    for m in measurements[1:]:
        curr_dt = parse_timestamp(current_group["timestamp"])
        next_dt = parse_timestamp(m["timestamp"])

        if curr_dt and next_dt and (next_dt - curr_dt).total_seconds() < 300:
            current_group["metrics"].update(m["metrics"])
        else:
            windowed.append(current_group)
            current_group = {"timestamp": m["timestamp"], "metrics": m["metrics"].copy()}

    windowed.append(current_group)
    return windowed


def convert_to_garmin(measurements):
    garmin_records = []
    for data in measurements:
        metrics = data["metrics"]
        ts = data["timestamp"]

        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M:%S")
        except Exception:
            continue

        garmin_record = {"date": date_str, "time": time_str}

        if "Weight (lbs)" in metrics:
            garmin_record["weight"] = round(float(metrics["Weight (lbs)"]) * 0.453592, 2)
        elif "Weight (kg)" in metrics:
            garmin_record["weight"] = float(metrics["Weight (kg)"])

        if "Body Fat %" in metrics:
            garmin_record["percent_fat"] = float(metrics["Body Fat %"])
        if "Moisture %" in metrics:
            garmin_record["percent_hydration"] = float(metrics["Moisture %"])
        if "Bone Mass" in metrics:
            garmin_record["bone_mass"] = float(metrics["Bone Mass"])

        if "Muscle %" in metrics and "weight" in garmin_record:
            weight_kg = float(metrics["Weight (lbs)"]) * 0.453592
            garmin_record["muscle_mass"] = round(weight_kg * float(metrics["Muscle %"]) / 100, 2)

        if "Visceral Fat" in metrics:
            try:
                garmin_record["visceral_fat_rating"] = int(float(metrics["Visceral Fat"]))
            except ValueError:
                pass

        if "BMI" in metrics:
            garmin_record["bmi"] = float(metrics["BMI"])

        if "weight" in garmin_record:
            garmin_records.append(garmin_record)

    return garmin_records


def upload_to_garmin(records, email, password):
    """Upload records to Garmin Connect with rate limiting."""
    try:
        from garminconnect import Garmin
    except ImportError:
        print("\n❌ garminconnect not installed")
        print("\nSet up a venv and install:")
        print("  python3 -m venv .venv")
        print("  source .venv/bin/activate")
        print("  pip install garminconnect")
        return False

    garmin = Garmin(email, password)
    try:
        garmin.login(tokenstore=".garminconnect")
    except Exception as e:
        print(f"\n❌ Login failed: {e}")
        return False

    print("\n=== Uploading to Garmin Connect ===")
    print("✓ Logged in successfully\n")

    success = failed = 0
    rate_limited = False

    for i, rec in enumerate(records, 1):
        ts = rec.get("date", "") + " " + rec.get("time", "")
        weight = rec.get("weight", "?")

        try:
            garmin.add_body_composition(**rec)
            print(f"✓ {ts} - {weight}kg")
            success += 1
        except Exception as e:
            if "429" in str(e):
                rate_limited = True
                print(f"\n  Rate limited! Waiting 60 seconds...")
                time.sleep(60)
                try:
                    garmin.add_body_composition(**rec)
                    print(f"✓ {ts} - {weight}kg (retry)")
                    success += 1
                except Exception:
                    print(f"✗ {ts} - Failed after retry")
                    failed += 1
            else:
                print(f"✗ {ts} - {e}")
                failed += 1

        if i < len(records):
            delay = 2 + (i % 3)
            time.sleep(delay)

    print(f"\n=== Upload Complete ===")
    print(f"✓ Uploaded: {success}")
    print(f"✗ Failed: {failed}")

    if rate_limited:
        print("\n⚠️  You were rate limited. Wait 15-30 minutes before uploading more.")

    return success > 0


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "Scale MD Pro.csv"

    print("=== Oxiline to Garmin Converter ===\n")

    print(f"Parsing {csv_path}...")
    measurements = parse_oxiline_csv(csv_path)
    print(f"Found {len(measurements)} measurement sessions\n")

    garmin_records = convert_to_garmin(measurements)
    print(f"Converted {len(garmin_records)} records\n")

    if garmin_records:
        print("=== Sample records ===")
        for i, rec in enumerate(garmin_records[:5], 1):
            ts = rec["date"] + "T" + rec["time"] + "Z"
            print(f"{i}. {ts}")
            if "weight" in rec:
                print(f"   Weight: {rec['weight']} kg")
            if "percent_fat" in rec:
                print(f"   Body Fat: {rec['percent_fat']}%")
            if "percent_hydration" in rec:
                print(f"   Hydration: {rec['percent_hydration']}%")
            if "muscle_mass" in rec:
                print(f"   Muscle: {rec['muscle_mass']} kg")
            if "bone_mass" in rec:
                print(f"   Bone: {rec['bone_mass']} kg")
            if "visceral_fat_rating" in rec:
                print(f"   Visceral Fat: {rec['visceral_fat_rating']}")
            if "bmi" in rec:
                print(f"   BMI: {rec['bmi']}")

        if len(garmin_records) > 5:
            print(f"\n... and {len(garmin_records) - 5} more records")

    all_metrics = set()
    for m in measurements:
        all_metrics.update(m["metrics"].keys())

    kept = {"Weight (lbs)", "Weight (kg)", "Body Fat %", "Moisture %", "Bone Mass", "Muscle %", "Visceral Fat", "BMI"}
    lost = all_metrics - kept

    if lost:
        print(f"\n=== {len(lost)} metrics NOT supported by Garmin ===")
        print("\nGarmin API accepts:")
        print("  weight, fat %, hydration %, bone mass")
        print("  muscle mass, visceral fat, BMI")

    output = "garmin_body_composition.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(garmin_records, f, indent=2)
    print(f"\n✓ Saved {len(garmin_records)} records to {output}")

    print("\n" + "=" * 60)
    if input("Upload to Garmin Connect now? (y/n): ").strip().lower() == "y":
        print("\n" + "=" * 60)
        email = input("Garmin email: ").strip()
        password = getpass.getpass("Garmin password: ")
        upload_to_garmin(garmin_records, email, password)


if __name__ == "__main__":
    main()