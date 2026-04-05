#!/usr/bin/env python3
"""Compare service-intelligence scan outputs against gold-standard ECG exports."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICE_INTELLIGENCE_ROOT = PROJECT_ROOT / "service-intelligence"
if str(SERVICE_INTELLIGENCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_INTELLIGENCE_ROOT))

from app.services.morphology_processor import process_morphology_frames  # noqa: E402
from app.services.rppg_processor import FrameSample, process_frames  # noqa: E402


@dataclass(frozen=True)
class EcgSample:
    timestamp_ms: float
    hr_bpm: float
    rr_ms: float | None


@dataclass(frozen=True)
class ValidationWindow:
    start_ms: float
    end_ms: float
    estimated_hr_bpm: float
    reference_hr_bpm: float
    absolute_error_bpm: float
    estimated_hrv_ms: float | None
    reference_hrv_ms: float | None
    absolute_error_hrv_ms: float | None
    quality_score: float


@dataclass(frozen=True)
class ValidationSummary:
    windows_evaluated: int
    mean_absolute_error_bpm: float | None
    rmse_bpm: float | None
    mean_absolute_error_hrv_ms: float | None
    rmse_hrv_ms: float | None
    mean_quality_score: float | None
    hr_threshold_bpm: float
    hrv_threshold_ms: float | None
    passes_threshold: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate service-intelligence HR/HRV outputs against a gold-standard ECG CSV.",
    )
    parser.add_argument("--trace-csv", required=True, type=Path)
    parser.add_argument("--ecg-csv", required=True, type=Path)
    parser.add_argument("--scan-type", choices=("standard", "deep_dive"), default="standard")
    parser.add_argument("--user-height-cm", type=float, help="Required only for deep_dive stiffness index.")
    parser.add_argument("--trace-time-column", default="t_ms")
    parser.add_argument("--trace-r-column", default="r_mean")
    parser.add_argument("--trace-g-column", default="g_mean")
    parser.add_argument("--trace-b-column", default="b_mean")
    parser.add_argument("--ecg-time-column", default="timestamp_ms")
    parser.add_argument("--ecg-hr-column", default="hr_bpm")
    parser.add_argument("--ecg-rr-column", default="rr_ms")
    parser.add_argument("--window-seconds", type=float, default=10.0)
    parser.add_argument("--stride-seconds", type=float, default=5.0)
    parser.add_argument("--hr-threshold-bpm", type=float, default=5.0)
    parser.add_argument("--hrv-threshold-ms", type=float)
    parser.add_argument("--preserve-original-timestamps", action="store_true")
    parser.add_argument("--output-json", type=Path)
    return parser.parse_args()


def load_trace_samples(
    path: Path,
    time_column: str,
    r_column: str,
    g_column: str,
    b_column: str,
) -> list[FrameSample]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [
            FrameSample(
                t_ms=float(row[time_column]),
                r_mean=float(row[r_column]),
                g_mean=float(row[g_column]),
                b_mean=float(row[b_column]),
            )
            for row in reader
        ]


def load_ecg_samples(
    path: Path,
    time_column: str,
    hr_column: str,
    rr_column: str,
) -> list[EcgSample]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows: list[EcgSample] = []
        for row in reader:
            rr_value = row.get(rr_column)
            rows.append(
                EcgSample(
                    timestamp_ms=float(row[time_column]),
                    hr_bpm=float(row[hr_column]),
                    rr_ms=float(rr_value) if rr_value not in (None, "") else None,
                )
            )
        return rows


def normalise_trace_samples(samples: list[FrameSample]) -> list[FrameSample]:
    if not samples:
        return samples
    offset = samples[0].t_ms
    return [
        FrameSample(
            t_ms=sample.t_ms - offset,
            r_mean=sample.r_mean,
            g_mean=sample.g_mean,
            b_mean=sample.b_mean,
        )
        for sample in samples
    ]


def normalise_ecg_samples(samples: list[EcgSample]) -> list[EcgSample]:
    if not samples:
        return samples
    offset = samples[0].timestamp_ms
    return [
        EcgSample(
            timestamp_ms=sample.timestamp_ms - offset,
            hr_bpm=sample.hr_bpm,
            rr_ms=sample.rr_ms,
        )
        for sample in samples
    ]


def validate_against_ecg(
    trace_samples: list[FrameSample],
    ecg_samples: list[EcgSample],
    scan_type: str,
    window_seconds: float,
    stride_seconds: float,
    user_height_cm: float | None,
) -> list[ValidationWindow]:
    if not trace_samples:
        raise ValueError("No RGB trace samples were loaded.")
    if not ecg_samples:
        raise ValueError("No ECG samples were loaded.")

    window_ms = window_seconds * 1000.0
    stride_ms = stride_seconds * 1000.0
    last_trace_ms = trace_samples[-1].t_ms

    windows: list[ValidationWindow] = []
    start_ms = 0.0
    while start_ms + window_ms <= last_trace_ms + 1e-6:
        end_ms = start_ms + window_ms
        trace_window = [sample for sample in trace_samples if start_ms <= sample.t_ms < end_ms]
        ecg_window = [sample for sample in ecg_samples if start_ms <= sample.timestamp_ms < end_ms]

        if trace_window and ecg_window:
            if scan_type == "deep_dive":
                result = process_morphology_frames(trace_window, user_height_cm=user_height_cm)
                estimated_hr = result.hr_bpm
                estimated_hrv = result.hrv_ms
                quality_score = result.quality_score
            else:
                result = process_frames(trace_window)
                estimated_hr = result.hr_bpm
                estimated_hrv = result.hrv_ms
                quality_score = result.quality_score

            if estimated_hr is not None:
                reference_hr = fmean(sample.hr_bpm for sample in ecg_window)
                reference_hrv = _reference_rmssd(ecg_window)
                hrv_error = (
                    abs(estimated_hrv - reference_hrv)
                    if estimated_hrv is not None and reference_hrv is not None
                    else None
                )
                windows.append(
                    ValidationWindow(
                        start_ms=start_ms,
                        end_ms=end_ms,
                        estimated_hr_bpm=estimated_hr,
                        reference_hr_bpm=reference_hr,
                        absolute_error_bpm=abs(estimated_hr - reference_hr),
                        estimated_hrv_ms=estimated_hrv,
                        reference_hrv_ms=reference_hrv,
                        absolute_error_hrv_ms=hrv_error,
                        quality_score=quality_score,
                    )
                )

        start_ms += stride_ms

    return windows


def _reference_rmssd(ecg_window: list[EcgSample]) -> float | None:
    rr_values = [sample.rr_ms for sample in ecg_window if sample.rr_ms is not None]
    if len(rr_values) < 3:
        return None
    rr_diffs = [rr_values[index + 1] - rr_values[index] for index in range(len(rr_values) - 1)]
    return round(math.sqrt(fmean(diff * diff for diff in rr_diffs)), 3)


def summarise_validation(
    windows: list[ValidationWindow],
    hr_threshold_bpm: float,
    hrv_threshold_ms: float | None,
) -> ValidationSummary:
    if not windows:
        return ValidationSummary(
            windows_evaluated=0,
            mean_absolute_error_bpm=None,
            rmse_bpm=None,
            mean_absolute_error_hrv_ms=None,
            rmse_hrv_ms=None,
            mean_quality_score=None,
            hr_threshold_bpm=hr_threshold_bpm,
            hrv_threshold_ms=hrv_threshold_ms,
            passes_threshold=False,
        )

    hr_errors = [window.absolute_error_bpm for window in windows]
    hrv_errors = [
        window.absolute_error_hrv_ms
        for window in windows
        if window.absolute_error_hrv_ms is not None
    ]
    hr_mae = fmean(hr_errors)
    hr_rmse = math.sqrt(fmean(error * error for error in hr_errors))
    hrv_mae = fmean(hrv_errors) if hrv_errors else None
    hrv_rmse = math.sqrt(fmean(error * error for error in hrv_errors)) if hrv_errors else None
    mean_quality = fmean(window.quality_score for window in windows)
    passes_hr = hr_mae <= hr_threshold_bpm
    passes_hrv = hrv_threshold_ms is None or (
        hrv_mae is not None and hrv_mae <= hrv_threshold_ms
    )
    return ValidationSummary(
        windows_evaluated=len(windows),
        mean_absolute_error_bpm=round(hr_mae, 3),
        rmse_bpm=round(hr_rmse, 3),
        mean_absolute_error_hrv_ms=round(hrv_mae, 3) if hrv_mae is not None else None,
        rmse_hrv_ms=round(hrv_rmse, 3) if hrv_rmse is not None else None,
        mean_quality_score=round(mean_quality, 3),
        hr_threshold_bpm=hr_threshold_bpm,
        hrv_threshold_ms=hrv_threshold_ms,
        passes_threshold=passes_hr and passes_hrv,
    )


def main() -> int:
    args = parse_args()

    trace_samples = load_trace_samples(
        args.trace_csv,
        args.trace_time_column,
        args.trace_r_column,
        args.trace_g_column,
        args.trace_b_column,
    )
    ecg_samples = load_ecg_samples(
        args.ecg_csv,
        args.ecg_time_column,
        args.ecg_hr_column,
        args.ecg_rr_column,
    )

    if not args.preserve_original_timestamps:
        trace_samples = normalise_trace_samples(trace_samples)
        ecg_samples = normalise_ecg_samples(ecg_samples)

    windows = validate_against_ecg(
        trace_samples,
        ecg_samples,
        args.scan_type,
        args.window_seconds,
        args.stride_seconds,
        args.user_height_cm,
    )
    summary = summarise_validation(
        windows,
        hr_threshold_bpm=args.hr_threshold_bpm,
        hrv_threshold_ms=args.hrv_threshold_ms,
    )

    print(f"Windows evaluated: {summary.windows_evaluated}")
    if summary.mean_absolute_error_bpm is None:
        print("No comparable windows were produced. Check timestamps, coverage, and signal quality.")
    else:
        print(f"HR MAE: {summary.mean_absolute_error_bpm:.3f} bpm")
        print(f"HR RMSE: {summary.rmse_bpm:.3f} bpm")
        if summary.mean_absolute_error_hrv_ms is not None:
            print(f"HRV MAE: {summary.mean_absolute_error_hrv_ms:.3f} ms")
            print(f"HRV RMSE: {summary.rmse_hrv_ms:.3f} ms")
        print(f"Mean quality score: {summary.mean_quality_score:.3f}")
        print(f"Pass thresholds: {summary.passes_threshold}")

    if args.output_json:
        payload = {
            "summary": asdict(summary),
            "windows": [asdict(window) for window in windows],
        }
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return 0 if summary.passes_threshold else 1


if __name__ == "__main__":
    raise SystemExit(main())
