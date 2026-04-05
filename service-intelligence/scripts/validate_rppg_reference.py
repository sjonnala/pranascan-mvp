#!/usr/bin/env python3
"""Validate the POS rPPG pipeline against a reference heart-rate device export."""

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
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.rppg_processor import FrameSample, process_frames  # noqa: E402


@dataclass(frozen=True)
class ReferenceSample:
    timestamp_ms: float
    hr_bpm: float


@dataclass(frozen=True)
class ValidationWindow:
    start_ms: float
    end_ms: float
    estimated_hr_bpm: float
    reference_hr_bpm: float
    absolute_error_bpm: float
    quality_score: float


@dataclass(frozen=True)
class ValidationSummary:
    windows_evaluated: int
    mean_absolute_error_bpm: float | None
    rmse_bpm: float | None
    mean_quality_score: float | None
    threshold_bpm: float
    passes_threshold: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare RGB-trace rPPG output against a reference HR device export.",
    )
    parser.add_argument("--trace-csv", required=True, type=Path, help="CSV with t_ms,r_mean,g_mean,b_mean")
    parser.add_argument("--reference-csv", required=True, type=Path, help="CSV with timestamp and reference HR")
    parser.add_argument("--trace-time-column", default="t_ms")
    parser.add_argument("--trace-r-column", default="r_mean")
    parser.add_argument("--trace-g-column", default="g_mean")
    parser.add_argument("--trace-b-column", default="b_mean")
    parser.add_argument("--reference-time-column", default="timestamp_ms")
    parser.add_argument("--reference-hr-column", default="hr_bpm")
    parser.add_argument("--window-seconds", type=float, default=10.0)
    parser.add_argument("--stride-seconds", type=float, default=5.0)
    parser.add_argument("--threshold-bpm", type=float, default=5.0)
    parser.add_argument(
        "--preserve-original-timestamps",
        action="store_true",
        help="Do not normalise both traces to start at 0 ms before alignment.",
    )
    parser.add_argument("--output-json", type=Path, help="Optional JSON summary output path.")
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


def load_reference_samples(
    path: Path,
    time_column: str,
    hr_column: str,
) -> list[ReferenceSample]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [
            ReferenceSample(
                timestamp_ms=float(row[time_column]),
                hr_bpm=float(row[hr_column]),
            )
            for row in reader
        ]


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


def normalise_reference_samples(samples: list[ReferenceSample]) -> list[ReferenceSample]:
    if not samples:
        return samples
    offset = samples[0].timestamp_ms
    return [
        ReferenceSample(
            timestamp_ms=sample.timestamp_ms - offset,
            hr_bpm=sample.hr_bpm,
        )
        for sample in samples
    ]


def validate_against_reference(
    trace_samples: list[FrameSample],
    reference_samples: list[ReferenceSample],
    window_seconds: float,
    stride_seconds: float,
) -> list[ValidationWindow]:
    if not trace_samples:
        raise ValueError("No RGB trace samples were loaded.")
    if not reference_samples:
        raise ValueError("No reference samples were loaded.")

    window_ms = window_seconds * 1000.0
    stride_ms = stride_seconds * 1000.0
    last_trace_ms = trace_samples[-1].t_ms

    windows: list[ValidationWindow] = []
    start_ms = 0.0
    while start_ms + window_ms <= last_trace_ms + 1e-6:
        end_ms = start_ms + window_ms
        trace_window = [sample for sample in trace_samples if start_ms <= sample.t_ms < end_ms]
        reference_window = [
            sample.hr_bpm
            for sample in reference_samples
            if start_ms <= sample.timestamp_ms < end_ms
        ]

        if trace_window and reference_window:
            result = process_frames(trace_window)
            if result.hr_bpm is not None:
                reference_hr = fmean(reference_window)
                absolute_error = abs(result.hr_bpm - reference_hr)
                windows.append(
                    ValidationWindow(
                        start_ms=start_ms,
                        end_ms=end_ms,
                        estimated_hr_bpm=result.hr_bpm,
                        reference_hr_bpm=reference_hr,
                        absolute_error_bpm=absolute_error,
                        quality_score=result.quality_score,
                    )
                )

        start_ms += stride_ms

    return windows


def summarise_validation(
    windows: list[ValidationWindow],
    threshold_bpm: float,
) -> ValidationSummary:
    if not windows:
        return ValidationSummary(
            windows_evaluated=0,
            mean_absolute_error_bpm=None,
            rmse_bpm=None,
            mean_quality_score=None,
            threshold_bpm=threshold_bpm,
            passes_threshold=False,
        )

    squared_errors = [window.absolute_error_bpm ** 2 for window in windows]
    mae = fmean(window.absolute_error_bpm for window in windows)
    rmse = math.sqrt(fmean(squared_errors))
    mean_quality = fmean(window.quality_score for window in windows)
    return ValidationSummary(
        windows_evaluated=len(windows),
        mean_absolute_error_bpm=round(mae, 3),
        rmse_bpm=round(rmse, 3),
        mean_quality_score=round(mean_quality, 3),
        threshold_bpm=threshold_bpm,
        passes_threshold=mae <= threshold_bpm,
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
    reference_samples = load_reference_samples(
        args.reference_csv,
        args.reference_time_column,
        args.reference_hr_column,
    )

    if not args.preserve_original_timestamps:
        trace_samples = normalise_trace_samples(trace_samples)
        reference_samples = normalise_reference_samples(reference_samples)

    windows = validate_against_reference(
        trace_samples,
        reference_samples,
        args.window_seconds,
        args.stride_seconds,
    )
    summary = summarise_validation(windows, args.threshold_bpm)

    print(f"Windows evaluated: {summary.windows_evaluated}")
    if summary.mean_absolute_error_bpm is None:
        print("No comparable windows were produced. Check timestamps, coverage, and signal quality.")
    else:
        print(f"Mean absolute error: {summary.mean_absolute_error_bpm:.3f} bpm")
        print(f"RMSE: {summary.rmse_bpm:.3f} bpm")
        print(f"Mean quality score: {summary.mean_quality_score:.3f}")
        print(f"Pass threshold ({summary.threshold_bpm:.1f} bpm): {summary.passes_threshold}")

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
