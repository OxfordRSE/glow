# Test Data

This directory contains **minimal demo data** for quick testing.

## Files

- `demo_data.csv` — 21 rows (10 students, 2 waves, 2 schools) with minimal BeWell items

## Usage

Use this for quick smoke tests without generating large synthetic datasets:

```bash
# Seed the demo data into ODK Central
cd deploy/scripts
python seed_odk_test_data.py \
  --csv ../../testdata/demo_data.csv \
  --odk-url http://localhost:8080 \
  --email admin@example.com \
  --password your-password \
  --project-id 1
```

## Note

This dataset has **very limited BeWell items** (only `phq9_1`, `phq9_2`, `phq9_3`). For realistic testing with the full 140+ question set, use [glow-dummies](https://github.com/OxfordRSE/glow-dummies) to generate `data/data.csv` instead (see `data/README.md`).
