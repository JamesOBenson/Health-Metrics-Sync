# Health Metrics Sync

Sync body composition data from Oxiline scales to Garmin Connect.

## Quick Start

```bash
# Recommended: Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

pip install garminconnect
python3 oxiline_to_garmin.py "Scale MD Pro.csv"
```

When prompted, type `y` to upload automatically.

## Interactive Upload

The script will:
1. Parse your Oxiline CSV
2. Show sample records
3. Ask if you want to upload
4. Prompt for your Garmin credentials
5. Upload all records automatically

```
$ python3 oxiline_to_garmin.py
=== Oxiline to Garmin Converter ===
...
✓ Saved 31 records to garmin_body_composition.json

==================================================
Upload to Garmin Connect now? (y/n): y

==================================================
Garmin email: your@email.com
Garmin password: ********

=== Uploading to Garmin Connect ===
✓ Logged in successfully

✓ 2026-09-13T13:36:56 - 66.52kg
✓ 2026-09-16T10:34:39 - 66.34kg
...

=== Upload Complete ===
✓ Uploaded: 31
✗ Failed: 0
```

## Manual Upload (if automatic fails)

```bash
pip install garminconnect
```

```python
from garminconnect import Garmin
import json

garmin = Garmin('your@email.com', 'password')
garmin.login(tokenstore='.garminconnect')

with open('garmin_body_composition.json') as f:
    for rec in json.load(f):
        garmin.add_body_composition(**rec)
```

## What Gets Uploaded (7 fields)

| Oxiline Metric | Garmin Field |
|---------------|--------------|
| Weight (lbs) | weight (kg) |
| Body Fat % | percent_fat |
| Moisture % | percent_hydration |
| Bone Mass | bone_mass |
| Muscle % | muscle_mass (estimated) |
| Visceral Fat | visceral_fat_rating |
| BMI | bmi |

## What Doesn't Upload (28 metrics)

Garmin's API only accepts 7 fields. These Oxiline metrics **cannot** be uploaded:
- Segmental measurements (arm/leg/trunk fat & muscle)
- BMR, Physical Age, Obesity Degree
- Protein %, Skeletal Muscle %, Waist-Hip Ratio
- And 20+ others

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

| Method | Fields | Credentials | Speed |
|--------|--------|-------------|-------|
| **API** (`oxiline_to_garmin.py`) | 7 fields | Required | ~2 min (with delays) |
| **CSV** (`create_garmin_csv.py`) | 3 fields | Not needed | Instant |

**Recommendation**: Use API method for complete data transfer.