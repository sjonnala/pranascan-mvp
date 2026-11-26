"""Classical rPPG baseline comparison helpers."""

from __future__ import annotations

import argparse
import csv
import inspect
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import signal

from app.services import rppg_processor
from app.services.rppg_processor import FrameSample

from .common import (
    ensure_output_dir,
    generate_synthetic_frames,
    get_scenario_config,
    load_frame_samples_csv,
    write_json,
)
from .dsp_lab import maybe_render_plot, regularize_rgb_trace


@dataclass(frozen=True)
class BaselineEstimate:
    """HR estimate and diagnostics for one classical baseline."""

    method: str
    hr_bpm: float | None
    hrv_ms: float | None
    quality_score: float
    dominant_frequency_hz: float | None
    flags: list[str]


def compare_methods(frames: list[FrameSample]) -> dict[str, BaselineEstimate]:
    """Compare green-only, ICA, CHROM, and POS on one RGB trace."""
    regular_timestamps, regular_rgb, sample_rate_hz, flags = regularize_rgb_trace(frames)
    del regular_timestamps  # timestamps are not needed outside metric estimation

    detrended_rgb = rppg_processor._detrend_linear(regular_rgb)
    relative_rgb = _relative_rgb(regular_rgb)
    detrended_relative_rgb = rppg_processor._detrend_linear(relative_rgb)

    estimates = {
        "green": _estimate_signal(
            "green",
            detrended_rgb[:, 1],
            sample_rate_hz,
            flags,
        ),
        "chrom": _estimate_signal(
            "chrom",
            _chrom_waveform(detrended_relative_rgb),
            sample_rate_hz,
            flags,
        ),
        "pos": _estimate_signal(
            "pos",
            pos_waveform(regular_rgb, sample_rate_hz),
            sample_rate_hz,
            flags,
        ),
        "ica": _estimate_ica_signal(detrended_relative_rgb, sample_rate_hz, flags),
    }
    return estimates


def pos_waveform(regular_rgb: np.ndarray, sample_rate_hz: float) -> np.ndarray:
    """POS pulse signal from the raw, uniformly resampled RGB trace.

    POS normalises each channel by its own temporal mean (Wang et al. 2017), so it
    must receive raw RGB. A linearly detrended trace has a near-zero mean, which
    makes that division unstable. The output is detrended afterwards, matching the
    production order in PR #1 (``_detrend_linear(_extract_pos_waveform(rgb, fs))``).

    ``sample_rate_hz`` is forwarded when the production function accepts it (the
    windowed POS in PR #1, ``sample_rate_hz=UPSAMPLE_TARGET_FS`` by default). The
    current global POS takes ``rgb`` only, so the call stays compatible with both.
    """
    extract = rppg_processor._extract_pos_waveform
    if _accepts_sample_rate(extract):
        waveform = extract(regular_rgb, sample_rate_hz=sample_rate_hz)
    else:
        waveform = extract(regular_rgb)
    return rppg_processor._detrend_linear(np.asarray(waveform, dtype=np.float64))


def _accepts_sample_rate(function: object) -> bool:
    try:
        parameters = inspect.signature(function).parameters  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if "sample_rate_hz" in parameters:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values())


def write_baseline_report(
    output_dir: str | Path,
    report: dict[str, BaselineEstimate],
) -> None:
    """Persist the baseline comparison as CSV and JSON."""
    destination = ensure_output_dir(output_dir)
    with (destination / "baseline_comparison.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "method",
                "hr_bpm",
                "hrv_ms",
                "quality_score",
                "dominant_frequency_hz",
                "flags",
            ],
        )
        writer.writeheader()
        for estimate in report.values():
            writer.writerow(
                {
                    "method": estimate.method,
                    "hr_bpm": estimate.hr_bpm,
                    "hrv_ms": estimate.hrv_ms,
                    "quality_score": estimate.quality_score,
                    "dominant_frequency_hz": estimate.dominant_frequency_hz,
                    "flags": ",".join(estimate.flags),
                }
            )

    write_json(
        destination / "baseline_comparison.json",
        {
            method: {
                "hr_bpm": estimate.hr_bpm,
                "hrv_ms": estimate.hrv_ms,
                "quality_score": estimate.quality_score,
                "dominant_frequency_hz": estimate.dominant_frequency_hz,
                "flags": estimate.flags,
            }
            for method, estimate in report.items()
        },
    )


def _estimate_signal(
    method: str,
    raw_trace: np.ndarray,
    sample_rate_hz: float,
    carry_flags: list[str],
) -> BaselineEstimate:
    flags = list(carry_flags)
    std = float(np.std(raw_trace))
    if std < 1e-6:
        flags.append("flat_signal")
        return BaselineEstimate(method, None, None, 0.0, None, flags)

    normalized_trace = raw_trace / std
    filtered_trace = rppg_processor._bandpass_signal(
        normalized_trace,
        sample_rate_hz,
        rppg_processor.HR_LOW_HZ,
        rppg_processor.HR_HIGH_HZ,
    )
    if filtered_trace is None:
        flags.append("filter_error")
        return BaselineEstimate(method, None, None, 0.0, None, flags)

    total_power = float(np.mean(normalized_trace**2))
    cardiac_power = float(np.mean(filtered_trace**2))
    quality_score = round(
        min(cardiac_power / total_power, 1.0) if total_power > 1e-9 else 0.0,
        4,
    )
    if quality_score < rppg_processor.MIN_SPECTRAL_QUALITY:
        flags.append("low_signal_quality")

    dominant_frequency_hz = rppg_processor._dominant_frequency(
        filtered_trace,
        sample_rate_hz,
        rppg_processor.HR_LOW_HZ,
        rppg_processor.HR_HIGH_HZ,
    )
    if dominant_frequency_hz is None:
        flags.append("insufficient_peaks")
        return BaselineEstimate(method, None, None, quality_score, None, flags)

    prominence = max(0.01, float(np.std(filtered_trace)) * 0.08)
    min_peak_distance = max(
        1,
        int(rppg_processor.PEAK_DISTANCE_FRACTION * sample_rate_hz / dominant_frequency_hz),
    )
    peaks, _ = signal.find_peaks(
        filtered_trace,
        distance=min_peak_distance,
        prominence=prominence,
    )
    if len(peaks) < 3:
        flags.append("insufficient_peaks")
        return BaselineEstimate(method, None, None, quality_score, dominant_frequency_hz, flags)

    peak_times = peaks / sample_rate_hz
    ibi_s = np.diff(peak_times)
    mean_ibi_s = float(np.mean(ibi_s))
    hr_bpm = round(60.0 / mean_ibi_s, 1) if mean_ibi_s > 0 else None

    hrv_ms = None
    if len(ibi_s) >= 3:
        rr_diffs_ms = np.diff(ibi_s * 1000.0)
        hrv_ms = round(float(np.sqrt(np.mean(rr_diffs_ms**2))), 2)

    return BaselineEstimate(method, hr_bpm, hrv_ms, quality_score, dominant_frequency_hz, flags)


def _estimate_ica_signal(
    detrended_relative_rgb: np.ndarray,
    sample_rate_hz: float,
    carry_flags: list[str],
) -> BaselineEstimate:
    components = _fast_ica_components(detrended_relative_rgb)
    if components is None:
        return BaselineEstimate("ica", None, None, 0.0, None, [*carry_flags, "ica_failed"])

    best_estimate: BaselineEstimate | None = None
    for index in range(components.shape[1]):
        estimate = _estimate_signal(
            "ica",
            components[:, index],
            sample_rate_hz,
            carry_flags,
        )
        if best_estimate is None:
            best_estimate = estimate
            continue
        if estimate.hr_bpm is not None and estimate.quality_score >= best_estimate.quality_score:
            best_estimate = estimate

    if best_estimate is None:
        return BaselineEstimate("ica", None, None, 0.0, None, [*carry_flags, "ica_failed"])
    return best_estimate


def _relative_rgb(rgb: np.ndarray) -> np.ndarray:
    channel_mean = np.mean(rgb, axis=0, keepdims=True)
    channel_mean[channel_mean == 0.0] = 1.0
    return (rgb / channel_mean) - 1.0


def _chrom_waveform(detrended_relative_rgb: np.ndarray) -> np.ndarray:
    x_component = (3.0 * detrended_relative_rgb[:, 0]) - (2.0 * detrended_relative_rgb[:, 1])
    y_component = (
        1.5 * detrended_relative_rgb[:, 0]
        + detrended_relative_rgb[:, 1]
        - 1.5 * detrended_relative_rgb[:, 2]
    )
    y_std = float(np.std(y_component))
    alpha = float(np.std(x_component) / y_std) if y_std > 1e-6 else 0.0
    return rppg_processor._detrend_linear(x_component - (alpha * y_component))


def _fast_ica_components(
    x: np.ndarray,
    max_iter: int = 400,
    tol: float = 1e-6,
    seed: int = 7,
) -> np.ndarray | None:
    n_samples, n_features = x.shape
    x_centered = x - np.mean(x, axis=0, keepdims=True)
    covariance = np.cov(x_centered, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)

    valid = eigenvalues > 1e-9
    if int(np.sum(valid)) < n_features:
        return None

    whitening = eigenvectors[:, valid] @ np.diag(1.0 / np.sqrt(eigenvalues[valid]))
    x_white = x_centered @ whitening

    rng = np.random.default_rng(seed)
    weights = rng.normal(size=(n_features, n_features))
    weights = _sym_decorrelation(weights)

    for _ in range(max_iter):
        projection = x_white @ weights.T
        non_linear = np.tanh(projection)
        derivative = 1.0 - (non_linear**2)
        updated = (non_linear.T @ x_white) / n_samples - np.diag(
            np.mean(derivative, axis=0)
        ) @ weights
        updated = _sym_decorrelation(updated)
        delta = np.max(np.abs(np.abs(np.diag(updated @ weights.T)) - 1.0))
        weights = updated
        if delta < tol:
            break

    return x_white @ weights.T


def _sym_decorrelation(weights: np.ndarray) -> np.ndarray:
    left, _, right = np.linalg.svd(weights, full_matrices=False)
    return left @ right


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="hr_80")
    parser.add_argument("--input-csv", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()

    if args.input_csv is not None:
        frames = load_frame_samples_csv(args.input_csv)
    else:
        frames = generate_synthetic_frames(get_scenario_config(args.scenario))

    report = compare_methods(frames)
    write_baseline_report(args.output_dir, report)

    if args.plot:
        from .dsp_lab import run_pipeline_stages

        rendered = maybe_render_plot(
            Path(args.output_dir) / "pipeline.png",
            run_pipeline_stages(frames),
        )
        if not rendered:
            print("matplotlib is not installed; skipping pipeline.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
