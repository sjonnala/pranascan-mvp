"""Shared helpers for the Phase 1 learning lab."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.services.rppg_processor import FrameSample


@dataclass(frozen=True)
class SyntheticScenarioConfig:
    """Configuration for a deterministic synthetic RGB trace."""

    hr_bpm: float = 72.0
    fps: float = 30.0
    duration_s: float = 30.0
    noise_std: float = 0.15
    channel_amplitudes: tuple[float, float, float] = (1.0, 2.0, 0.5)
    illumination_hz: float = 0.08
    illumination_amplitude: float = 0.25
    motion_hz: float = 0.33
    motion_amplitude: float = 0.0
    signal_scale: float = 1.0
    brightness_offset: float = 0.0
    irregular_timestamps: bool = False
    flat_signal: bool = False
    seed: int = 42


def scenario_catalog() -> dict[str, SyntheticScenarioConfig]:
    """Named scenarios used across the learning track."""
    return {
        "hr_60": SyntheticScenarioConfig(hr_bpm=60.0),
        "hr_80": SyntheticScenarioConfig(hr_bpm=80.0),
        "hr_100": SyntheticScenarioConfig(hr_bpm=100.0, noise_std=0.18),
        "low_fps": SyntheticScenarioConfig(hr_bpm=55.0, fps=20.0, noise_std=0.08),
        "high_noise": SyntheticScenarioConfig(hr_bpm=72.0, noise_std=1.2),
        "low_light": SyntheticScenarioConfig(
            hr_bpm=72.0,
            noise_std=0.35,
            signal_scale=0.55,
            brightness_offset=-22.0,
        ),
        "motion": SyntheticScenarioConfig(
            hr_bpm=72.0,
            noise_std=0.22,
            motion_amplitude=0.75,
        ),
        "irregular_timestamps": SyntheticScenarioConfig(
            hr_bpm=72.0,
            irregular_timestamps=True,
        ),
        "flat_signal": SyntheticScenarioConfig(flat_signal=True),
    }


def get_scenario_config(name: str) -> SyntheticScenarioConfig:
    """Look up a named scenario or raise a helpful error."""
    catalog = scenario_catalog()
    if name not in catalog:
        available = ", ".join(sorted(catalog))
        raise ValueError(f"Unknown scenario '{name}'. Available scenarios: {available}")
    return catalog[name]


def generate_synthetic_frames(config: SyntheticScenarioConfig) -> list[FrameSample]:
    """Generate RGB frame samples with controlled pulse and nuisance factors."""
    sample_count = int(config.fps * config.duration_s)
    timeline_s = np.arange(sample_count, dtype=np.float64) / config.fps
    base_timestamp_ms = timeline_s * 1000.0

    if config.flat_signal:
        signal_rgb = np.column_stack(
            [
                np.full(sample_count, 96.0 + config.brightness_offset),
                np.full(sample_count, 112.0 + config.brightness_offset),
                np.full(sample_count, 82.0 + config.brightness_offset),
            ]
        )
        return [
            FrameSample(
                t_ms=float(base_timestamp_ms[index]),
                r_mean=float(signal_rgb[index, 0]),
                g_mean=float(signal_rgb[index, 1]),
                b_mean=float(signal_rgb[index, 2]),
            )
            for index in range(sample_count)
        ]

    rng = np.random.default_rng(config.seed)
    pulse_frequency_hz = config.hr_bpm / 60.0
    pulse = np.sin(2.0 * math.pi * pulse_frequency_hz * timeline_s)
    harmonic = 0.35 * np.sin(4.0 * math.pi * pulse_frequency_hz * timeline_s)
    illumination = config.illumination_amplitude * np.sin(
        2.0 * math.pi * config.illumination_hz * timeline_s
    )
    motion = config.motion_amplitude * np.sin(2.0 * math.pi * config.motion_hz * timeline_s)
    random_motion = rng.normal(0.0, config.motion_amplitude * 0.12, sample_count)

    amplitudes = np.asarray(config.channel_amplitudes, dtype=np.float64) * config.signal_scale
    red = 96.0 + config.brightness_offset + amplitudes[0] * pulse + illumination + motion
    green = (
        112.0
        + config.brightness_offset
        + amplitudes[1] * pulse
        + 0.2 * harmonic
        + illumination
        + motion
    )
    blue = (
        82.0
        + config.brightness_offset
        + amplitudes[2] * pulse
        - 0.15 * harmonic
        + illumination
        + 0.7 * motion
    )

    red += 0.45 * random_motion + rng.normal(0.0, config.noise_std, sample_count)
    green += random_motion + rng.normal(0.0, config.noise_std, sample_count)
    blue += 0.35 * random_motion + rng.normal(0.0, config.noise_std, sample_count)

    timestamps_ms = base_timestamp_ms.copy()
    if config.irregular_timestamps and len(timestamps_ms) >= 16:
        timestamps_ms[15] = timestamps_ms[10]

    return [
        FrameSample(
            t_ms=float(timestamps_ms[index]),
            r_mean=float(red[index]),
            g_mean=float(green[index]),
            b_mean=float(blue[index]),
        )
        for index in range(sample_count)
    ]


def ensure_output_dir(path: str | Path) -> Path:
    """Create an output directory and return it."""
    output_dir = Path(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_frame_samples_csv(path: str | Path, frames: list[FrameSample]) -> None:
    """Persist frame samples using the repo's canonical RGB-trace contract."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["t_ms", "r_mean", "g_mean", "b_mean"])
        writer.writeheader()
        for frame in frames:
            writer.writerow(
                {
                    "t_ms": round(frame.t_ms, 4),
                    "r_mean": round(frame.r_mean, 6),
                    "g_mean": round(frame.g_mean, 6),
                    "b_mean": round(frame.b_mean, 6),
                }
            )


def load_frame_samples_csv(
    path: str | Path,
    columns: dict[str, str] | None = None,
) -> list[FrameSample]:
    """Load frame samples from a CSV with configurable column names."""
    source = Path(path)
    mapping = columns or {
        "t_ms": "t_ms",
        "r_mean": "r_mean",
        "g_mean": "g_mean",
        "b_mean": "b_mean",
    }
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [
            FrameSample(
                t_ms=float(row[mapping["t_ms"]]),
                r_mean=float(row[mapping["r_mean"]]),
                g_mean=float(row[mapping["g_mean"]]),
                b_mean=float(row[mapping["b_mean"]]),
            )
            for row in reader
        ]


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    """Write JSON with stable formatting."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def scenario_config_to_dict(config: SyntheticScenarioConfig) -> dict[str, Any]:
    """Convert a scenario config into a JSON-friendly dict."""
    payload = asdict(config)
    payload["channel_amplitudes"] = list(config.channel_amplitudes)
    return payload
