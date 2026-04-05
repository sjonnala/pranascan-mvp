# rPPG Reference Validation

Use the offline validation harness in `service-intelligence/scripts/validate_rppg_reference.py` to compare the POS rPPG pipeline against a reference device such as:

- Apple Watch export with timestamped heart rate
- Pulse oximeter export with timestamped BPM values
- Polar/strap export converted to CSV with `timestamp_ms` and `hr_bpm`

## Required Inputs

### RGB trace CSV

Expected columns by default:

```csv
t_ms,r_mean,g_mean,b_mean
0,96.1,112.8,82.4
33.3,96.0,112.6,82.3
66.7,96.2,113.0,82.5
```

### Reference HR CSV

Expected columns by default:

```csv
timestamp_ms,hr_bpm
0,71
1000,72
2000,72
```

## Run

```bash
cd service-intelligence
./.venv/bin/python scripts/validate_rppg_reference.py \
  --trace-csv /path/to/rgb_trace.csv \
  --reference-csv /path/to/reference_hr.csv \
  --window-seconds 10 \
  --stride-seconds 5 \
  --threshold-bpm 5 \
  --output-json /tmp/rppg-validation.json
```

By default the harness normalises both inputs so each starts at `0 ms`. If both exports already share a common absolute timeline, add:

```bash
--preserve-original-timestamps
```

## Output

The script prints:

- window count used for comparison
- mean absolute error in BPM
- RMSE in BPM
- mean signal-quality score
- pass/fail against the target threshold

Exit status:

- `0` when `MAE <= threshold`
- `1` when the threshold is missed or no comparable windows are produced

## Target

The current acceptance goal for the upgraded 30 FPS pipeline is:

- `MAE < 5 BPM` against the reference device

Do not treat synthetic test results as validation evidence. The harness is only meaningful when run against a real recorded RGB trace and a real reference-device export from the same session.
