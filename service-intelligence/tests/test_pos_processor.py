"""Unit tests for the POS RGB-trace processor."""

from __future__ import annotations

import math

import numpy as np

from app.services.pos_processor import extract_bvp, process_rgb_traces
from app.services.rppg_processor import FrameSample


def _make_rgb_trace(
    hr_bpm: float = 72.0,
    fps: float = 30.0,
    duration_s: float = 30.0,
    noise_std: float = 0.15,
    seed: int = 42,
) -> list[FrameSample]:
    rng = np.random.default_rng(seed)
    sample_count = int(fps * duration_s)
    t = np.arange(sample_count) / fps
    pulse = np.sin(2.0 * math.pi * (hr_bpm / 60.0) * t)

    red = 96.0 + 1.0 * pulse + rng.normal(0.0, noise_std, sample_count)
    green = 112.0 + 2.0 * pulse + rng.normal(0.0, noise_std, sample_count)
    blue = 82.0 + 0.5 * pulse + rng.normal(0.0, noise_std, sample_count)

    return [
        FrameSample(
            t_ms=float(t[index] * 1000.0),
            r_mean=float(red[index]),
            g_mean=float(green[index]),
            b_mean=float(blue[index]),
        )
        for index in range(sample_count)
    ]


def test_extract_bvp_returns_regularised_signal():
    signal = extract_bvp(_make_rgb_trace())

    assert signal.sample_rate_hz >= 30.0
    assert signal.timestamps_s.shape == signal.bvp.shape
    assert 0.0 <= signal.quality_score <= 1.0


def test_pos_processor_recovers_72_bpm_trace():
    result = process_rgb_traces(_make_rgb_trace(hr_bpm=72.0))

    assert result.hr_bpm is not None
    assert abs(result.hr_bpm - 72.0) <= 6.0
    assert result.hrv_ms is not None


def test_pos_processor_recovers_90_bpm_trace():
    result = process_rgb_traces(_make_rgb_trace(hr_bpm=90.0, noise_std=0.2))

    assert result.hr_bpm is not None
    assert abs(result.hr_bpm - 90.0) <= 8.0


def test_low_framerate_trace_is_upsampled():
    result = process_rgb_traces(_make_rgb_trace(hr_bpm=55.0, fps=20.0, noise_std=0.1))

    assert "low_framerate_upsampled" in result.flags
    assert result.hr_bpm is not None
    assert abs(result.hr_bpm - 55.0) <= 8.0


def test_insufficient_trace_returns_flag():
    result = process_rgb_traces(_make_rgb_trace(duration_s=3.0))

    assert result.hr_bpm is None
    assert "insufficient_frames" in result.flags or "insufficient_temporal_span" in result.flags
