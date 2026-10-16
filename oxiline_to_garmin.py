#!/usr/bin/env python3
"""Convert Oxiline Scale CSV to Garmin Connect format and upload."""

import csv
import json
from datetime import datetime
import sys
import re
import getpass
import time


def detect_csv_type(csv_path):
    """Detect if CSV is body composition or blood pressure."""
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            header = f.readline().lower()
            if "systolic" in header or "diastolic" in header:
                return "blood_pressure"
            elif "weight" in header or "body fat" in header or "metric" in header:
                return "body_composition"
    except Exception:
        pass
    return "body_composition"


def parse_blood_pressure_csv(csv_path):
    """Parse OMRON blood pressure CSV."""
    readings = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                date_str = row.get("Date", "")
                time_str = row.get("Time", "")

                if not date_str or not time_str:
                    continue

                datetime_str = f"{date_str}, {time_str}"
                dt = datetime.strptime(datetime_str, "%b %d %Y, %I:%M %p")
                timestamp = dt.isoformat()

                reading = {
                    "timestamp": timestamp,
                    "systolic": int(row.get("Systolic (mmHg)", 0)),
                    "diastolic": int(row.get("Diastolic (mmHg)", 0)),
                }

                pulse = row.get("Pulse (bpm)", "")
                if pulse:
                    reading["pulse"] = int(pulse)

                notes = row.get("Notes", "")
                if notes and notes != "-":
                    reading["notes"] = notes

                readings.append(reading)
            except Exception:
                continue

    return readings


def parse_oxiline_csv(csv_path):
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
    first = measurements[0]
    current_group = {"timestamp": first["timestamp"], "metrics": first["metrics"].copy()}

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
            timestamp = dt.isoformat()
        except Exception:
            continue

        garmin_record = {"timestamp": timestamp}

        if "Weight (lbs)" in metrics:
            garmin_record["weight"] = round(
                float(metrics["Weight (lbs)"]) * 0.453592, 2
            )
        elif "Weight (kg)" in metrics:
            garmin_record["weight"] = round(float(metrics["Weight (kg)"]), 2)

        if "Body Fat %" in metrics:
            garmin_record["percent_fat"] = float(metrics["Body Fat %"])
        if "Moisture %" in metrics:
            garmin_record["percent_hydration"] = float(metrics["Moisture %"])
        if "Bone Mass" in metrics:
            garmin_record["bone_mass"] = float(metrics["Bone Mass"])

        if "Muscle %" in metrics and "weight" in garmin_record:
            weight_kg = float(metrics["Weight (lbs)"]) * 0.453592
            garmin_record["muscle_mass"] = round(
                weight_kg * float(metrics["Muscle %"]) / 100, 2
            )

        if "Visceral Fat" in metrics:
            try:
                garmin_record["visceral_fat_rating"] = int(
                    float(metrics["Visceral Fat"])
                )
            except ValueError:
                pass

        if "BMI" in metrics:
            garmin_record["bmi"] = float(metrics["BMI"])

        if "weight" in garmin_record:
            garmin_records.append(garmin_record)

    return garmin_records


def load_credentials():
    """Load credentials from .creds file."""
    email = None
    password = None
    try:
        with open(".creds", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith('USERNAME="'):
                    email = line.split('="')[1].rstrip('"')
                elif line.startswith('PASSWORD="'):
                    password = line.split('="')[1].rstrip('"')
            return email, password
    except FileNotFoundError:
        return None, None


def upload_blood_pressure(records, email, password, force_upload=False):
    """Upload blood pressure records to Garmin Connect."""
    try:
        from garminconnect import Garmin, GarminConnectTooManyRequestsError
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
        if "429" in str(e) or "TooManyRequests" in str(e):
            print("\n❌ Rate limited on login!")
            print("   Wait 15-30 minutes before trying again.")
            print("   Or delete .garminconnect and try with fresh credentials.")
        else:
            print(f"\n❌ Login failed: {e}")
        return False

    print("\n=== Uploading Blood Pressure to Garmin Connect ===")
    print("✓ Logged in successfully\n")

    existing_timestamps = set()
    if not force_upload and records:
        print("Checking for duplicates...")
        dates = [rec.get("timestamp", "")[:10] for rec in records]
        start_date = min(dates)
        end_date = max(dates)
        try:
            existing_data = garmin.get_blood_pressure(start_date, end_date)
            # API returns: {"measurementSummaries": [{"measurements": [...], ...}, ...]}
            if isinstance(existing_data, dict):
                summaries = existing_data.get("measurementSummaries", [])
                if isinstance(summaries, list):
                    for summary in summaries:
                        if isinstance(summary, dict):
                            measurements = summary.get("measurements", [])
                            if isinstance(measurements, list):
                                for m in measurements:
                                    if isinstance(m, dict):
                                        # Use measurementTimestampLocal for comparison
                                        ts = m.get("measurementTimestampLocal", "")
                                        if ts:
                                            # Truncate to seconds for comparison
                                            existing_timestamps.add(ts[:19])
            if existing_timestamps:
                print(f"  Found {len(existing_timestamps)} existing reading(s)\n")
            else:
                print("  No existing data found\n")
        except Exception as e:
            print(f"  ⚠️  Could not check existing data: {e}")
            print("  Proceeding with upload...\n")
    elif force_upload:
        print("⚠️  Force mode: skipping duplicate check\n")

    success = failed = skipped = 0

    for rec in records:
        ts = rec.get("timestamp", "")[:19]
        systolic = rec.get("systolic", "?")
        diastolic = rec.get("diastolic", "?")
        full_ts = rec.get("timestamp", "")

        # Check if this exact timestamp exists
        if full_ts in existing_timestamps:
            print(f"⊘ {ts} - {systolic}/{diastolic} (duplicate)")
            skipped += 1
            continue

        try:
            garmin.set_blood_pressure(
                systolic=rec["systolic"],
                diastolic=rec["diastolic"],
                pulse=rec.get("pulse"),
                timestamp=rec["timestamp"],
                notes=rec.get("notes", ""),
            )
            print(f"✓ {ts} - {systolic}/{diastolic}")
            success += 1
        except GarminConnectTooManyRequestsError:
            print("\n⚠️  Rate limited! Waiting 30 seconds...")
            time.sleep(30)
            try:
                garmin.set_blood_pressure(
                    systolic=rec["systolic"],
                    diastolic=rec["diastolic"],
                    pulse=rec.get("pulse"),
                    timestamp=rec["timestamp"],
                    notes=rec.get("notes", ""),
                )
                print(f"✓ {ts} - {systolic}/{diastolic} (retry)")
                success += 1
            except Exception as e:
                print(f"✗ {ts} - {e}")
                failed += 1
        except Exception as e:
            print(f"✗ {ts} - {e}")
            failed += 1

    print("\n=== Upload Complete ===")
    print(f"✓ Uploaded: {success}")
    print(f"⊘ Skipped: {skipped}")
    print(f"✗ Failed: {failed}")

    return success > 0


def upload_to_garmin(records, email, password, force_upload=False):
    """Upload body composition records to Garmin Connect."""
    try:
        from garminconnect import Garmin, GarminConnectTooManyRequestsError
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
        if "429" in str(e) or "TooManyRequests" in str(e):
            print("\n❌ Rate limited on login!")
            print("   Wait 15-30 minutes before trying again.")
            print("   Or delete .garminconnect and try with fresh credentials.")
        else:
            print(f"\n❌ Login failed: {e}")
        return False

    print("\n=== Uploading to Garmin Connect ===")
    print("✓ Logged in successfully\n")

    existing_dates = set()
    if not force_upload and records:
        print("Checking for duplicates...")
        dates = [rec.get("timestamp", "")[:10] for rec in records]
        start_date = min(dates)
        end_date = max(dates)
        try:
            existing_data = garmin.get_body_composition(start_date, end_date)
            if isinstance(existing_data, dict):
                date_weight_list = existing_data.get("dateWeightList", [])
                if isinstance(date_weight_list, list):
                    for entry in date_weight_list:
                        if isinstance(entry, dict):
                            ts = entry.get("calendarDate", "")
                            if ts:
                                existing_dates.add(ts)
            if existing_dates:
                print(f"  Found {len(existing_dates)} existing date(s)\n")
            else:
                print("  No existing data found\n")
        except Exception as e:
            print(f"  ⚠️  Could not check existing data: {e}")
            print("  Proceeding with upload...\n")
    elif force_upload:
        print("⚠️  Force mode: skipping duplicate check\n")

    success = failed = skipped = 0

    for rec in records:
        date = rec.get("timestamp", "")[:10]
        ts = rec.get("timestamp", "")[:19]
        weight = rec.get("weight", "?")

        if date in existing_dates:
            print(f"⊘ {ts} - {weight}kg (duplicate)")
            skipped += 1
            continue

        try:
            garmin.add_body_composition(**rec)
            print(f"✓ {ts} - {weight}kg")
            success += 1
        except GarminConnectTooManyRequestsError:
            print("\n⚠️  Rate limited! Waiting 30 seconds...")
            time.sleep(30)
            try:
                garmin.add_body_composition(**rec)
                print(f"✓ {ts} - {weight}kg (retry)")
                success += 1
            except Exception as e:
                print(f"✗ {ts} - {e}")
                failed += 1
        except Exception as e:
            print(f"✗ {ts} - {e}")
            failed += 1

    print("\n=== Upload Complete ===")
    print(f"✓ Uploaded: {success}")
    print(f"⊘ Skipped: {skipped}")
    print(f"✗ Failed: {failed}")

    return success > 0


def main():
    force_upload = "--force" in sys.argv
    csv_path = (
        sys.argv[1]
        if len(sys.argv) > 1 and sys.argv[1] != "--force"
        else "Scale MD Pro.csv"
    )

    print("=== Health Metrics to Garmin Converter ===")
    if force_upload:
        print("⚠️  FORCE MODE: Will upload all records, including duplicates\n")
    else:
        print()

    csv_type = detect_csv_type(csv_path)
    print(f"Detected: {csv_type.replace('_', ' ').title()}")

    if csv_type == "blood_pressure":
        records = parse_blood_pressure_csv(csv_path)
        print(f"Found {len(records)} readings\n")

        if records:
            print("=== Sample records ===")
            for i, rec in enumerate(records[:5], 1):
                ts = rec["timestamp"][:19]
                print(f"{i}. {ts}")
                print(f"   Blood Pressure: {rec['systolic']}/{rec['diastolic']}")
                if "pulse" in rec:
                    print(f"   Pulse: {rec['pulse']} bpm")

            if len(records) > 5:
                print(f"\n... and {len(records) - 5} more records")

        output = "garmin_blood_pressure.json"
        with open(output, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
        print(f"\n✓ Saved {len(records)} records to {output}")

        print("\n" + "=" * 60)
        if input("Upload to Garmin Connect now? (y/n): ").strip().lower() == "y":
            print("\n" + "=" * 60)

            email, password = load_credentials()
            if email and password:
                print("Using credentials from .creds file")
                print(f"Garmin email: {email}")
            else:
                email = input("Garmin email: ").strip()
                password = getpass.getpass("Garmin password: ")

            upload_blood_pressure(records, email, password, force_upload)

    else:
        measurements = parse_oxiline_csv(csv_path)
        print(f"Found {len(measurements)} measurement sessions\n")

        garmin_records = convert_to_garmin(measurements)
        print(f"Converted {len(garmin_records)} records\n")

        if garmin_records:
            print("=== Sample records ===")
            for i, rec in enumerate(garmin_records[:5], 1):
                ts = rec["timestamp"]
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

        kept = {
            "Weight (lbs)",
            "Weight (kg)",
            "Body Fat %",
            "Moisture %",
            "Bone Mass",
            "Muscle %",
            "Visceral Fat",
            "BMI",
        }
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

            email, password = load_credentials()
            if email and password:
                print("Using credentials from .creds file")
                print(f"Garmin email: {email}")
            else:
                email = input("Garmin email: ").strip()
                password = getpass.getpass("Garmin password: ")

            upload_to_garmin(garmin_records, email, password, force_upload)


if __name__ == "__main__":
    main()
