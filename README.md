# Health Metrics Sync

Sync body composition data and blood pressure readings from Oxiline/OMRON devices to Garmin Connect.

## Quick Start

```bash
# Recommended: Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

pip install garminconnect
python3 oxiline_to_garmin.py "Scale MD Pro.csv"  # Body composition
python3 oxiline_to_garmin.py "OMRON.csv"  # Blood pressure
```

The script auto-detects the CSV type and handles both body composition and blood pressure.

When prompted, type `y` to upload automatically.

## Optional: Store Credentials

To avoid entering credentials each time, create a `.creds` file:

```bash
cat > .creds << EOF
USERNAME="your@email.com"
PASSWORD="your_password"
EOF
```

The script will automatically use these credentials. **Note**: `.creds` is in `.gitignore` and won't be committed to git.

## Command Line Options

### Skip Duplicate Check (Force Upload)

```bash
python3 oxiline_to_garmin.py "Scale MD Pro.csv" --force
```

Uploads all records, including duplicates. Use this if you want to re-upload data that already exists.

## How It Works

1. **Parse CSV** - Reads your Oxiline scale export
2. **Convert** - Maps Oxiline metrics to Garmin format
3. **Check Duplicates** - Fetches existing data from Garmin
4. **Upload** - Only uploads new records (unless `--force`)

### Output Example

```
=== Oxiline to Garmin Converter ===

Parsing Scale MD Pro.csv...
Found 33 measurement sessions

Converted 31 records

=== Sample records ===
1. 2026-09-13T13:36:56+00:00
   Weight: 66.52 kg
   Body Fat: 12.2%
   Hydration: 64.3%
   ...

✓ Saved 31 records to garmin_body_composition.json

============================================================
Upload to Garmin Connect now? (y/n): y

============================================================
Using credentials from .creds file
Garmin email: your@email.com

=== Uploading to Garmin Connect ===
✓ Logged in successfully

Checking for duplicates...
  Found 24 existing date(s)

⊘ 2026-09-13T13:36:56 - 66.52kg (duplicate)
✓ 2026-09-15T10:30:00 - 66.30kg
...

=== Upload Complete ===
✓ Uploaded: 7
⊘ Skipped: 24
✗ Failed: 0
```

## What Gets Uploaded

### Body Composition (7 fields)

| Oxiline Metric | Garmin Field |
|---------------|--------------|
| Weight (lbs) | weight (kg) |
| Body Fat % | percent_fat |
| Moisture % | percent_hydration |
| Bone Mass | bone_mass |
| Muscle % | muscle_mass (estimated) |
| Visceral Fat | visceral_fat_rating |
| BMI | bmi |

### Blood Pressure (3 fields)

| OMRON Metric | Garmin Field |
|--------------|--------------|
| Systolic (mmHg) | systolic |
| Diastolic (mmHg) | diastolic |
| Pulse (bpm) | pulse (optional) |

## What Doesn't Upload

**Body Composition**: Garmin's API only accepts 7 fields. These Oxiline metrics **cannot** be uploaded:
- Segmental measurements (arm/leg/trunk fat & muscle)
- BMR, Physical Age, Obesity Degree
- Protein %, Skeletal Muscle %, Waist-Hip Ratio
- And 20+ others

**Blood Pressure**: Notes and symptoms are not uploaded to Garmin.

## Files

### Main Scripts

| File | Purpose |
|------|---------|
| `oxiline_to_garmin.py` | ✅ **Main script** - Converts + uploads automatically |
| `create_garmin_csv.py` | CSV converter - Creates file for manual web upload |

### Output Files

| File | Format | Use Case |
|------|--------|----------|
| `garmin_body_composition.json` | JSON | API upload (all 7 fields) |
| `garmin_upload.csv` | CSV | Web upload (3 fields only) |

---

## Alternative: CSV Upload Method

If you prefer **manual upload via web** (no API, no credentials needed):

### Step 1: Generate CSV

```bash
python3 create_garmin_csv.py
```

Creates `garmin_upload.csv` ready for Garmin Connect.

### Step 2: Upload to Garmin

1. Go to: **https://connect.garmin.com/modern/import-data**
2. Drag `garmin_upload.csv` into the import area
3. Click "Import Data"

### Limitations

CSV upload only supports **3 fields**:
- Weight
- BMI
- Body Fat %

**Lost data**: Hydration %, Bone Mass, Muscle Mass, Visceral Fat

---

## Comparison: API vs CSV Upload

| Method | Fields | Credentials | Speed | Duplicates |
|--------|--------|-------------|-------|------------|
| **API** (`oxiline_to_garmin.py`) | 7 fields | Required | ~3 sec | Auto-skip |
| **CSV** (`create_garmin_csv.py`) | 3 fields | Not needed | Instant | Manual |

**Recommendation**: Use API method for complete data transfer and automatic duplicate detection.