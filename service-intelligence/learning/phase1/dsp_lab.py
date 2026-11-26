"""Stage-by-stage inspection utilities for the current POS rPPG pipeline."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.interpolate import CubicSpline

from app.services import rppg_processor
from app.services.rppg_processor import FrameSample

from .common import (
    ensure_output_dir,
    generate_synthetic_frames,
    get_scenario_config,
    scenario_catalog,
    scenario_config_to_dict,
    write_frame_samples_csv,
    write_json,
)


@dataclass(frozen=True)
class PipelineStageArtifacts:
    """Intermediate signals and outcomes for one learning-lab run."""

    regular_timestamps_s: np.ndarray
    regular_rgb: np.ndarray
    detrended_rgb: np.ndarray
    pos_bvp: np.ndarray
    normalized_bvp: np.ndarray
    filtered_bvp: np.ndarray
    respiratory_band: np.ndarray | None
    peak_indices: np.ndarray
    sample_rate_hz: float
    quality_score: float
    dominant_frequency_hz: float | None
    hr_bpm: float | None
    hrv_ms: float | None
    respiratory_rate: float | None
    flags: list[str]


def regularize_rgb_trace(
    frames: list[FrameSample],
) -> tuple[np.ndarray, np.ndarray, float, list[str]]:
    """Apply the same timestamp validation and resampling logic as production."""
    flags: list[str] = []
    timestamps_s, rgb = rppg_processor._validate_and_materialize(frames)

    diffs = np.diff(timestamps_s)
    median_dt = float(np.median(diffs[diffs > 0]))
    sample_rate_hz = 1.0 / median_dt

    target_fs = sample_rate_hz
    if sample_rate_hz < rppg_processor.MIN_USEFUL_FS:
        target_fs = rppg_processor.UPSAMPLE_TARGET_FS
        flags.append("low_framerate_upsampled")

    regular_timestamps = np.arange(timestamps_s[0], timestamps_s[-1], 1.0 / target_fs)
    if regular_timestamps.size < rppg_processor.MIN_FRAMES:
        raise ValueError("insufficient_frames")

    if "low_framerate_upsampled" in flags:
        regular_rgb = np.column_stack(
            [CubicSpline(timestamps_s, rgb[:, index])(regular_timestamps) for index in range(3)]
        )
    else:
        regular_rgb = np.column_stack(
            [np.interp(regular_timestamps, timestamps_s, rgb[:, index]) for index in range(3)]
        )

    if float(np.max(np.std(regular_rgb, axis=0))) < 1e-3:
        raise ValueError("flat_signal")

    return regular_timestamps, regular_rgb, target_fs, flags


def run_pipeline_stages(frames: list[FrameSample]) -> PipelineStageArtifacts:
    """Run the current POS pipeline while retaining learning-friendly intermediates."""
    regular_timestamps, regular_rgb, sample_rate_hz, flags = regularize_rgb_trace(frames)
    detrended_rgb = rppg_processor._detrend_linear(regular_rgb)

    pos_bvp = rppg_processor._extract_pos_waveform(detrended_rgb)
    bvp_std = float(np.std(pos_bvp))
    if bvp_std < 1e-6:
        raise ValueError("flat_signal")

    normalized_bvp = pos_bvp / bvp_std
    filtered_bvp = rppg_processor._bandpass_signal(
        normalized_bvp,
        sample_rate_hz,
        rppg_processor.HR_LOW_HZ,
        rppg_processor.HR_HIGH_HZ,
    )
    if filtered_bvp is None:
        raise ValueError("filter_error")

    total_power = float(np.mean(normalized_bvp**2))
    cardiac_power = float(np.mean(filtered_bvp**2))
    quality_score = round(
        min(cardiac_power / total_power, 1.0) if total_power > 1e-9 else 0.0,
        4,
    )
    if quality_score < rppg_processor.MIN_SPECTRAL_QUALITY:
        flags.append("low_signal_quality")

    dominant_frequency_hz = rppg_processor._dominant_frequency(
        filtered_bvp,
        sample_rate_hz,
        rppg_processor.HR_LOW_HZ,
        rppg_processor.HR_HIGH_HZ,
    )

    hr_bpm = None
    hrv_ms = None
    peak_indices = np.array([], dtype=int)
    if dominant_frequency_hz is not None:
        prominence = max(0.01, float(np.std(filtered_bvp)) * 0.08)
        min_peak_distance = max(
            1,
            int(rppg_processor.PEAK_DISTANCE_FRACTION * sample_rate_hz / dominant_frequency_hz),
        )
        peak_indices, _ = signal.find_peaks(
            filtered_bvp,
            distance=min_peak_distance,
            prominence=prominence,
        )
        if len(peak_indices) >= 3:
            peak_times = regular_timestamps[peak_indices]
            ibi_s = np.diff(peak_times)
            mean_ibi_s = float(np.mean(ibi_s))
            hr_bpm = round(60.0 / mean_ibi_s, 1) if mean_ibi_s > 0 else None
            if len(ibi_s) >= 3:
                rr_diffs_ms = np.diff(ibi_s * 1000.0)
                hrv_ms = round(float(np.sqrt(np.mean(rr_diffs_ms**2))), 2)
        else:
            flags.append("insufficient_peaks")
    else:
        flags.append("insufficient_peaks")

    respiratory_band = rppg_processor._bandpass_signal(
        normalized_bvp,
        sample_rate_hz,
        rppg_processor.RESP_LOW_HZ,
        rppg_processor.RESP_HIGH_HZ,
    )
    respiratory_rate = rppg_processor._estimate_respiratory_rate(normalized_bvp, sample_rate_hz)

    return PipelineStageArtifacts(
        regular_timestamps_s=regular_timestamps,
        regular_rgb=regular_rgb,
        detrended_rgb=detrended_rgb,
        pos_bvp=pos_bvp,
        normalized_bvp=normalized_bvp,
        filtered_bvp=filtered_bvp,
        respiratory_band=respiratory_band,
        peak_indices=peak_indices,
        sample_rate_hz=sample_rate_hz,
        quality_score=quality_score,
        dominant_frequency_hz=dominant_frequency_hz,
        hr_bpm=hr_bpm,
        hrv_ms=hrv_ms,
        respiratory_rate=respiratory_rate,
        flags=flags,
    )


def write_pipeline_artifacts(
    output_dir: str | Path,
    scenario_name: str,
    frames: list[FrameSample],
    artifacts: PipelineStageArtifacts,
) -> None:
    """Persist the full learning-lab output set."""
    destination = ensure_output_dir(output_dir)
    write_frame_samples_csv(destination / "frames.csv", frames)
    _write_stage_csv(destination / "stages.csv", artifacts)
    write_json(
        destination / "summary.json",
        {
            "scenario": scenario_name,
            "sample_rate_hz": round(artifacts.sample_rate_hz, 4),
            "quality_score": artifacts.quality_score,
            "dominant_frequency_hz": (
                round(artifacts.dominant_frequency_hz, 4)
                if artifacts.dominant_frequency_hz is not None
                else None
            ),
            "hr_bpm": artifacts.hr_bpm,
            "hrv_ms": artifacts.hrv_ms,
            "respiratory_rate": artifacts.respiratory_rate,
            "flags": artifacts.flags,
        },
    )


def maybe_render_plot(path: str | Path, artifacts: PipelineStageArtifacts) -> bool:
    """Render a quick-look plot when matplotlib is available."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    timeline = artifacts.regular_timestamps_s
    fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)
    axes[0].plot(timeline, artifacts.regular_rgb[:, 0], label="R")
    axes[0].plot(timeline, artifacts.regular_rgb[:, 1], label="G")
    axes[0].plot(timeline, artifacts.regular_rgb[:, 2], label="B")
    axes[0].set_title("Regularized RGB Trace")
    axes[0].legend(loc="upper right")

    axes[1].plot(timeline, artifacts.detrended_rgb[:, 0], label="R detrended")
    axes[1].plot(timeline, artifacts.detrended_rgb[:, 1], label="G detrended")
    axes[1].plot(timeline, artifacts.detrended_rgb[:, 2], label="B detrended")
    axes[1].set_title("Detrended RGB Channels")
    axes[1].legend(loc="upper right")

    axes[2].plot(timeline, artifacts.pos_bvp, label="POS BVP")
    axes[2].plot(timeline, artifacts.filtered_bvp, label="Bandpassed BVP")
    if artifacts.peak_indices.size:
        axes[2].scatter(
            timeline[artifacts.peak_indices],
            artifacts.filtered_bvp[artifacts.peak_indices],
            color="red",
            s=20,
            label="Detected peaks",
        )
    axes[2].set_title("POS Projection And Cardiac Bandpass")
    axes[2].legend(loc="upper right")

    axes[3].plot(timeline, artifacts.normalized_bvp, label="Normalized BVP")
    if artifacts.respiratory_band is not None:
        axes[3].plot(timeline, artifacts.respiratory_band, label="Respiratory band")
    axes[3].set_title("Normalized Signal And Respiratory Proxy")
    axes[3].legend(loc="upper right")
    axes[3].set_xlabel("Time (s)")

    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return True


def _write_stage_csv(path: Path, artifacts: PipelineStageArtifacts) -> None:
    respiratory_band = (
        artifacts.respiratory_band
        if artifacts.respiratory_band is not None
        else np.full_like(artifacts.filtered_bvp, np.nan)
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "t_s",
                "regular_r",
                "regular_g",
                "regular_b",
                "detrended_r",
                "detrended_g",
                "detrended_b",
                "pos_bvp",
                "normalized_bvp",
                "filtered_bvp",
                "respiratory_band",
                "is_peak",
            ],
        )
        writer.writeheader()
        peak_index_set = {int(index) for index in artifacts.peak_indices.tolist()}
        for index, timestamp_s in enumerate(artifacts.regular_timestamps_s):
            writer.writerow(
                {
                    "t_s": round(float(timestamp_s), 6),
                    "regular_r": round(float(artifacts.regular_rgb[index, 0]), 6),
                    "regular_g": round(float(artifacts.regular_rgb[index, 1]), 6),
                    "regular_b": round(float(artifacts.regular_rgb[index, 2]), 6),
                    "detrended_r": round(float(artifacts.detrended_rgb[index, 0]), 6),
                    "detrended_g": round(float(artifacts.detrended_rgb[index, 1]), 6),
                    "detrended_b": round(float(artifacts.detrended_rgb[index, 2]), 6),
                    "pos_bvp": round(float(artifacts.pos_bvp[index]), 6),
                    "normalized_bvp": round(float(artifacts.normalized_bvp[index]), 6),
                    "filtered_bvp": round(float(artifacts.filtered_bvp[index]), 6),
                    "respiratory_band": (
                        round(float(respiratory_band[index]), 6)
                        if not np.isnan(respiratory_band[index])
                        else ""
                    ),
                    "is_peak": int(index in peak_index_set),
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="hr_80")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--list-scenarios", action="store_true")
    args = parser.parse_args()

    if args.list_scenarios:
        for name in sorted(scenario_catalog()):
            print(name)
        return 0

    config = get_scenario_config(args.scenario)
    frames = generate_synthetic_frames(config)
    artifacts = run_pipeline_stages(frames)
    write_pipeline_artifacts(args.output_dir, args.scenario, frames, artifacts)
    write_json(
        Path(args.output_dir) / "scenario.json",
        scenario_config_to_dict(config),
    )
    if args.plot:
        rendered = maybe_render_plot(Path(args.output_dir) / "pipeline.png", artifacts)
        if not rendered:
            print("matplotlib is not installed; skipping pipeline.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
