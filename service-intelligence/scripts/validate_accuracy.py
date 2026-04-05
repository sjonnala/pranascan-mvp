#!/usr/bin/env python3
"""
validate_accuracy.py — End-to-end accuracy validation harness.

Compares PranaScan service-intelligence outputs against a "Gold Standard"
ECG/reference CSV export covering three metrics:

  • HR BPM   — compared against ECG-derived RR-interval HR
  • HRV RMSSD — compared against ECG-derived RMSSD
  • Stiffness Index — compared against PTT-based reference (Deep Dive only)

Usage
-----
# Standard (facial rPPG) validation:
python scripts/validate_accuracy.py \\
    --trace-csv    /data/session_001_rgb_trace.csv \\
    --ecg-csv      /data/session_001_ecg_gold.csv \\
    --mode         standard \\
    --output-json  /tmp/validation_standard.json

# Deep Dive (contact PPG) validation:
python scripts/validate_accuracy.py \\
    --trace-csv    /data/session_001_contact_trace.csv \\
    --ecg-csv      /data/session_001_ecg_gold.csv \\
    --mode         deep_dive \\
    --height-cm    172.0 \\
    --output-json  /tmp/validation_deep_dive.json

Input CSVs
----------
RGB trace CSV (--trace-csv):
  t_ms, r_mean, g_mean, b_mean
  0, 96.1, 112.8, 82.4
  33.3, 96.0, 112.6, 82.3

ECG gold standard CSV (--ecg-csv):
  timestamp_ms, hr_bpm, hrv_rmssd_ms[, stiffness_index]
  0, 71.3, 44.2
  1000, 72.1, 43.8

  - timestamp_ms: absolute or relative (normalised to 0 by default)
  - stiffness_index column is optional; used only when --mode deep_dive

Output
------
Prints per-metric MAE/RMSE and pass/fail against thresholds.
Optionally writes a detailed JSON report with per-window breakdowns.

Exit codes
----------
  0 — all enabled metrics pass their thresholds
  1 — one or more metrics fail or produce no comparable windows

Thresholds (configurable via flags)
------------------------------------
  --hr-threshold-bpm      (default 5.0)
  --hrv-threshold-ms      (default 10.0)
  --si-threshold          (default 0.5)

Notes
-----
- The harness runs the full server-side algorithm stack (POS or morphology)
  rather than comparing pre-computed values, so it exercises exactly the
  same code path that runs in production.
- HRV RMSSD from rPPG has larger variance than from ECG leads; the 10 ms
  default threshold is intentionally generous at MVP stage.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.rppg_processor import FrameSample, RppgResult, process_frames  # noqa: E402
from app.services.morphology_processor import MorphologyResult, process_morphology_frames  # noqa: E402


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldWindow:
    """One sliding window of ECG gold-standard data."""
    start_ms: float
    end_ms: float
    hr_bpm: float
    hrv_rmssd_ms: Optional[float]
    stiffness_index: Optional[float]


@dataclass(frozen=True)
class ComparisonWindow:
    """Per-window comparison result between pipeline and ECG."""
    start_ms: float
    end_ms: float
    # Pipeline outputs
    pipeline_hr_bpm: Optional[float]
    pipeline_hrv_ms: Optional[float]
    pipeline_stiffness_index: Optional[float]
    pipeline_quality_score: float
    # Gold standard
    gold_hr_bpm: float
    gold_hrv_rmssd_ms: Optional[float]
    gold_stiffness_index: Optional[float]
    # Errors
    hr_abs_error_bpm: Optional[float]
    hrv_abs_error_ms: Optional[float]
    si_abs_error: Optional[float]


@dataclass(frozen=True)
class MetricSummary:
    windows: int
    mae: Optional[float]
    rmse: Optional[float]
    threshold: float
    passes: bool


@dataclass(frozen=True)
class ValidationReport:
    mode: str
    windows_attempted: int
    windows_used: int
    hr: MetricSummary
    hrv: MetricSummary
    stiffness_index: Optional[MetricSummary]
    mean_quality_score: Optional[float]
    overall_pass: bool


# ---------------------------------------------------------------------------
# CSV loaders
# ---------------------------------------------------------------------------


def load_trace(
    path: Path,
    t_col: str = "t_ms",
    r_col: str = "r_mean",
    g_col: str = "g_mean",
    b_col: str = "b_mean",
) -> list[FrameSample]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        samples = []
        for row in reader:
            samples.append(
                FrameSample(
                    t_ms=float(row[t_col]),
                    r_mean=float(row[r_col]),
                    g_mean=float(row[g_col]),
                    b_mean=float(row[b_col]),
                )
            )
    if not samples:
        raise ValueError(f"RGB trace CSV is empty: {path}")
    return samples


def load_ecg_gold(
    path: Path,
    t_col: str = "timestamp_ms",
    hr_col: str = "hr_bpm",
    hrv_col: str = "hrv_rmssd_ms",
    si_col: str = "stiffness_index",
) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = []
        for row in reader:
            entry: dict = {
                "timestamp_ms": float(row[t_col]),
                "hr_bpm": float(row[hr_col]),
                "hrv_rmssd_ms": float(row[hrv_col]) if hrv_col in fieldnames and row.get(hrv_col) else None,
                "stiffness_index": float(row[si_col]) if si_col in fieldnames and row.get(si_col) else None,
            }
            rows.append(entry)
    if not rows:
        raise ValueError(f"ECG gold CSV is empty: {path}")
    return rows


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def normalise_trace(samples: list[FrameSample]) -> list[FrameSample]:
    offset = samples[0].t_ms
    return [
        FrameSample(t_ms=s.t_ms - offset, r_mean=s.r_mean, g_mean=s.g_mean, b_mean=s.b_mean)
        for s in samples
    ]


def normalise_ecg(rows: list[dict]) -> list[dict]:
    offset = rows[0]["timestamp_ms"]
    return [{**r, "timestamp_ms": r["timestamp_ms"] - offset} for r in rows]


# ---------------------------------------------------------------------------
# Sliding-window comparison
# ---------------------------------------------------------------------------


def run_comparison(
    trace: list[FrameSample],
    ecg: list[dict],
    mode: str,
    height_cm: Optional[float],
    window_s: float,
    stride_s: float,
) -> list[ComparisonWindow]:
    window_ms = window_s * 1000.0
    stride_ms = stride_s * 1000.0
    last_ms = trace[-1].t_ms

    results: list[ComparisonWindow] = []
    start_ms = 0.0

    while start_ms + window_ms <= last_ms + 1e-6:
        end_ms = start_ms + window_ms

        trace_window = [s for s in trace if start_ms <= s.t_ms < end_ms]
        ecg_window = [r for r in ecg if start_ms <= r["timestamp_ms"] < end_ms]

        if not trace_window or not ecg_window:
            start_ms += stride_ms
            continue

        # Run pipeline
        if mode == "deep_dive":
            result: MorphologyResult | RppgResult = process_morphology_frames(trace_window, height_cm)
            pipeline_hr = result.hr_bpm
            pipeline_hrv = result.hrv_ms
            pipeline_si = result.stiffness_index if isinstance(result, MorphologyResult) else None
            quality = result.quality_score
        else:
            result = process_frames(trace_window)
            pipeline_hr = result.hr_bpm
            pipeline_hrv = result.hrv_ms
            pipeline_si = None
            quality = result.quality_score

        # Gold standard averages over window
        gold_hr = fmean(r["hr_bpm"] for r in ecg_window)
        gold_hrv_vals = [r["hrv_rmssd_ms"] for r in ecg_window if r["hrv_rmssd_ms"] is not None]
        gold_hrv = fmean(gold_hrv_vals) if gold_hrv_vals else None
        gold_si_vals = [r["stiffness_index"] for r in ecg_window if r.get("stiffness_index") is not None]
        gold_si = fmean(gold_si_vals) if gold_si_vals else None

        hr_err = abs(pipeline_hr - gold_hr) if pipeline_hr is not None else None
        hrv_err = abs(pipeline_hrv - gold_hrv) if (pipeline_hrv is not None and gold_hrv is not None) else None
        si_err = abs(pipeline_si - gold_si) if (pipeline_si is not None and gold_si is not None) else None

        results.append(ComparisonWindow(
            start_ms=start_ms,
            end_ms=end_ms,
            pipeline_hr_bpm=pipeline_hr,
            pipeline_hrv_ms=pipeline_hrv,
            pipeline_stiffness_index=pipeline_si,
            pipeline_quality_score=quality,
            gold_hr_bpm=gold_hr,
            gold_hrv_rmssd_ms=gold_hrv,
            gold_stiffness_index=gold_si,
            hr_abs_error_bpm=hr_err,
            hrv_abs_error_ms=hrv_err,
            si_abs_error=si_err,
        ))

        start_ms += stride_ms

    return results


# ---------------------------------------------------------------------------
# Metric summaries
# ---------------------------------------------------------------------------


def _metric_summary(
    errors: list[float],
    threshold: float,
) -> MetricSummary:
    if not errors:
        return MetricSummary(windows=0, mae=None, rmse=None, threshold=threshold, passes=False)
    mae = fmean(errors)
    rmse = math.sqrt(fmean(e ** 2 for e in errors))
    return MetricSummary(
        windows=len(errors),
        mae=round(mae, 3),
        rmse=round(rmse, 3),
        threshold=threshold,
        passes=mae <= threshold,
    )


def build_report(
    windows: list[ComparisonWindow],
    mode: str,
    hr_threshold: float,
    hrv_threshold: float,
    si_threshold: float,
) -> ValidationReport:
    hr_errors = [w.hr_abs_error_bpm for w in windows if w.hr_abs_error_bpm is not None]
    hrv_errors = [w.hrv_abs_error_ms for w in windows if w.hrv_abs_error_ms is not None]
    si_errors = [w.si_abs_error for w in windows if w.si_abs_error is not None]

    hr_summary = _metric_summary(hr_errors, hr_threshold)
    hrv_summary = _metric_summary(hrv_errors, hrv_threshold)
    si_summary = _metric_summary(si_errors, si_threshold) if mode == "deep_dive" else None

    quality_scores = [w.pipeline_quality_score for w in windows]
    mean_quality = round(fmean(quality_scores), 3) if quality_scores else None

    passes = [hr_summary.passes, hrv_summary.passes]
    if si_summary is not None:
        passes.append(si_summary.passes)

    return ValidationReport(
        mode=mode,
        windows_attempted=len(windows),
        windows_used=len(windows),
        hr=hr_summary,
        hrv=hrv_summary,
        stiffness_index=si_summary,
        mean_quality_score=mean_quality,
        overall_pass=all(passes),
    )


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------


def print_report(report: ValidationReport) -> None:
    sep = "─" * 62
    print(sep)
    print(f"  PranaScan Accuracy Validation  [{report.mode.upper()}]")
    print(sep)
    print(f"  Windows compared : {report.windows_used}")
    print(f"  Mean quality score: {report.mean_quality_score or 'N/A'}")
    print()

    def row(label: str, summary: MetricSummary) -> None:
        if summary.windows == 0:
            print(f"  {label:<26}  NO DATA")
            return
        status = "✅ PASS" if summary.passes else "❌ FAIL"
        print(
            f"  {label:<26}  MAE={summary.mae:.3f}  RMSE={summary.rmse:.3f}"
            f"  threshold={summary.threshold}  {status}"
        )

    row("HR (BPM)", report.hr)
    row("HRV RMSSD (ms)", report.hrv)
    if report.stiffness_index is not None:
        row("Stiffness Index", report.stiffness_index)

    print()
    overall = "✅  ALL METRICS PASS" if report.overall_pass else "❌  ONE OR MORE METRICS FAIL"
    print(f"  Overall: {overall}")
    print(sep)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Validate PranaScan pipeline outputs against ECG gold-standard data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--trace-csv", required=True, type=Path,
                   help="RGB trace CSV: t_ms, r_mean, g_mean, b_mean")
    p.add_argument("--ecg-csv", required=True, type=Path,
                   help="ECG gold CSV: timestamp_ms, hr_bpm, hrv_rmssd_ms[, stiffness_index]")
    p.add_argument("--mode", choices=["standard", "deep_dive"], default="standard",
                   help="standard = facial POS rPPG; deep_dive = contact PPG morphology")
    p.add_argument("--height-cm", type=float, default=None,
                   help="User height in cm (required for stiffness index in deep_dive mode)")

    # Column overrides
    p.add_argument("--trace-t-col", default="t_ms")
    p.add_argument("--trace-r-col", default="r_mean")
    p.add_argument("--trace-g-col", default="g_mean")
    p.add_argument("--trace-b-col", default="b_mean")
    p.add_argument("--ecg-t-col", default="timestamp_ms")
    p.add_argument("--ecg-hr-col", default="hr_bpm")
    p.add_argument("--ecg-hrv-col", default="hrv_rmssd_ms")
    p.add_argument("--ecg-si-col", default="stiffness_index")

    # Window params
    p.add_argument("--window-seconds", type=float, default=10.0)
    p.add_argument("--stride-seconds", type=float, default=5.0)

    # Thresholds
    p.add_argument("--hr-threshold-bpm", type=float, default=5.0,
                   help="MAE threshold for HR in BPM (default 5.0)")
    p.add_argument("--hrv-threshold-ms", type=float, default=10.0,
                   help="MAE threshold for HRV RMSSD in ms (default 10.0)")
    p.add_argument("--si-threshold", type=float, default=0.5,
                   help="MAE threshold for Stiffness Index (default 0.5 m/s)")

    p.add_argument("--preserve-timestamps", action="store_true",
                   help="Do not normalise both traces to start at 0 ms")
    p.add_argument("--output-json", type=Path, default=None,
                   help="Optional path to write detailed JSON report")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    trace = load_trace(
        args.trace_csv,
        t_col=args.trace_t_col,
        r_col=args.trace_r_col,
        g_col=args.trace_g_col,
        b_col=args.trace_b_col,
    )
    ecg = load_ecg_gold(
        args.ecg_csv,
        t_col=args.ecg_t_col,
        hr_col=args.ecg_hr_col,
        hrv_col=args.ecg_hrv_col,
        si_col=args.ecg_si_col,
    )

    if not args.preserve_timestamps:
        trace = normalise_trace(trace)
        ecg = normalise_ecg(ecg)

    if args.mode == "deep_dive" and args.height_cm is None:
        print("WARNING: --height-cm not provided; stiffness_index will not be validated.", file=sys.stderr)

    windows = run_comparison(
        trace=trace,
        ecg=ecg,
        mode=args.mode,
        height_cm=args.height_cm,
        window_s=args.window_seconds,
        stride_s=args.stride_seconds,
    )

    if not windows:
        print("No comparable windows produced. Check timestamp alignment and CSV coverage.", file=sys.stderr)
        return 1

    report = build_report(
        windows,
        mode=args.mode,
        hr_threshold=args.hr_threshold_bpm,
        hrv_threshold=args.hrv_threshold_ms,
        si_threshold=args.si_threshold,
    )

    print_report(report)

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "report": asdict(report),
            "windows": [asdict(w) for w in windows],
        }
        args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\n  JSON report written to: {args.output_json}")

    return 0 if report.overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

