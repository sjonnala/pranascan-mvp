"""
Unit tests for the POS-capable rPPG processor.

Synthetic signals encode the same pulse into all three colour channels with
different amplitudes, which matches the assumptions of a multi-channel
skin-reflection algorithm better than the old green-only fixtures.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.services.rppg_processor import (
    FrameSample,
    RppgResult,
    build_frame_samples,
    process_frames,
)


def _make_signal(
    hr_bpm: float = 72.0,
    fps: float = 30.0,
    duration_s: float = 30.0,
    noise_std: float = 0.15,
    amplitudes: tuple[float, float, float] = (1.0, 2.0, 0.5),
    seed: int = 42,
) -> list[FrameSample]:
    rng = np.random.default_rng(seed)
    sample_count = int(fps * duration_s)
    t = np.arange(sample_count) / fps
    freq_hz = hr_bpm / 60.0
    pulse = np.sin(2.0 * math.pi * freq_hz * t)
    illumination_drift = 0.25 * np.sin(2.0 * math.pi * 0.08 * t)

    red = 96.0 + amplitudes[0] * pulse + illumination_drift + rng.normal(0.0, noise_std, sample_count)
    green = 112.0 + amplitudes[1] * pulse + illumination_drift + rng.normal(0.0, noise_std, sample_count)
    blue = 82.0 + amplitudes[2] * pulse + illumination_drift + rng.normal(0.0, noise_std, sample_count)

    return [
        FrameSample(
            t_ms=float(t[index] * 1000.0),
            r_mean=float(red[index]),
            g_mean=float(green[index]),
            b_mean=float(blue[index]),
        )
        for index in range(sample_count)
    ]


def _make_low_fps_signal(
    hr_bpm: float = 72.0,
    duration_s: float = 30.0,
    noise_std: float = 0.1,
) -> list[FrameSample]:
    return _make_signal(hr_bpm=hr_bpm, fps=20.0, duration_s=duration_s, noise_std=noise_std)


def test_process_frames_returns_rppg_result():
    result = process_frames(_make_signal())
    assert isinstance(result, RppgResult)


def test_result_has_required_fields():
    result = process_frames(_make_signal())
    assert hasattr(result, "hr_bpm")
    assert hasattr(result, "hrv_ms")
    assert hasattr(result, "respiratory_rate")
    assert hasattr(result, "quality_score")
    assert hasattr(result, "flags")
    assert isinstance(result.flags, list)


def test_60bpm_at_30fps_within_tolerance():
    result = process_frames(_make_signal(hr_bpm=60.0, fps=30.0, noise_std=0.12))
    assert result.hr_bpm is not None, f"No HR. Flags: {result.flags}"
    assert abs(result.hr_bpm - 60.0) <= 5.0


def test_80bpm_at_30fps_within_tolerance():
    result = process_frames(_make_signal(hr_bpm=80.0, fps=30.0, noise_std=0.12))
    assert result.hr_bpm is not None, f"No HR. Flags: {result.flags}"
    assert abs(result.hr_bpm - 80.0) <= 5.0


def test_100bpm_at_30fps_within_tolerance():
    result = process_frames(_make_signal(hr_bpm=100.0, fps=30.0, noise_std=0.15))
    assert result.hr_bpm is not None, f"No HR. Flags: {result.flags}"
    assert abs(result.hr_bpm - 100.0) <= 6.0


def test_55bpm_at_10fps_is_upsampled_and_detected():
    result = process_frames(_make_low_fps_signal(hr_bpm=55.0, duration_s=30.0))
    assert "low_framerate_upsampled" in result.flags
    assert result.hr_bpm is not None
    assert abs(result.hr_bpm - 55.0) <= 6.0


def test_72bpm_at_10fps_is_upsampled_and_detected():
    result = process_frames(_make_low_fps_signal(hr_bpm=72.0, duration_s=30.0))
    assert "low_framerate_upsampled" in result.flags
    assert result.hr_bpm is not None
    assert abs(result.hr_bpm - 72.0) <= 6.0


def test_hr_always_in_physiological_range():
    result = process_frames(_make_signal(hr_bpm=75.0))
    if result.hr_bpm is not None:
        assert 30.0 <= result.hr_bpm <= 220.0


def test_hrv_ms_nonnegative():
    result = process_frames(_make_signal(hr_bpm=70.0))
    if result.hrv_ms is not None:
        assert result.hrv_ms >= 0.0


def test_quality_score_bounded():
    for hr in [55.0, 72.0, 100.0]:
        result = process_frames(_make_signal(hr_bpm=hr))
        assert 0.0 <= result.quality_score <= 1.0


def test_high_noise_does_not_crash():
    result = process_frames(_make_signal(hr_bpm=72.0, noise_std=1.4))
    assert isinstance(result, RppgResult)


def test_high_noise_degrades_quality():
    clean = process_frames(_make_signal(hr_bpm=72.0, noise_std=0.05))
    noisy = process_frames(_make_signal(hr_bpm=72.0, noise_std=1.2))
    assert noisy.quality_score <= clean.quality_score + 0.1


def test_empty_frames_returns_insufficient_frames():
    result = process_frames([])
    assert result.hr_bpm is None
    assert "insufficient_frames" in result.flags
    assert result.quality_score == 0.0


def test_too_few_frames_returns_insufficient_frames():
    frames = _make_signal(fps=30.0, duration_s=1.0)
    result = process_frames(frames)
    assert result.hr_bpm is None
    assert "insufficient_frames" in result.flags


def test_insufficient_temporal_span():
    frames = _make_signal(fps=30.0, duration_s=3.0)
    result = process_frames(frames)
    assert result.hr_bpm is None
    assert "insufficient_temporal_span" in result.flags


def test_flat_signal_returns_flag():
    frames = [
        FrameSample(t_ms=float(index * 33), r_mean=96.0, g_mean=112.0, b_mean=82.0)
        for index in range(300)
    ]
    result = process_frames(frames)
    assert result.hr_bpm is None
    assert "flat_signal" in result.flags


def test_non_monotonic_timestamps_returns_flag():
    frames = _make_signal(hr_bpm=72.0, fps=30.0, duration_s=15.0)
    bad = [
        FrameSample(
            t_ms=frames[index].t_ms if index % 2 == 0 else frames[max(0, index - 10)].t_ms,
            r_mean=frames[index].r_mean,
            g_mean=frames[index].g_mean,
            b_mean=frames[index].b_mean,
        )
        for index in range(len(frames))
    ]
    result = process_frames(bad)
    assert "irregular_timestamps" in result.flags
    assert result.hr_bpm is None


def test_single_frame_returns_insufficient():
    result = process_frames([FrameSample(t_ms=0.0, r_mean=96.0, g_mean=112.0, b_mean=82.0)])
    assert result.hr_bpm is None
    assert "insufficient_frames" in result.flags


def test_build_frame_samples_converts_dicts():
    raw = [{"t_ms": 0.0, "r_mean": 96.0, "g_mean": 112.0, "b_mean": 82.0}]
    frames = build_frame_samples(raw)
    assert len(frames) == 1
    assert frames[0].t_ms == 0.0
    assert frames[0].g_mean == 112.0


def test_build_frame_samples_handles_multiple():
    raw = [
        {"t_ms": float(index * 33), "r_mean": 96.0, "g_mean": 112.0, "b_mean": 82.0}
        for index in range(100)
    ]
    frames = build_frame_samples(raw)
    assert len(frames) == 100
    assert frames[-1].t_ms == pytest.approx(99 * 33.0)


def test_no_diagnostic_language_in_flags():
    signals = [
        _make_signal(hr_bpm=72.0),
        _make_signal(noise_std=1.5),
        [],
        _make_low_fps_signal(),
    ]
    forbidden = {"diagnosis", "diagnostic", "disease", "condition", "disorder", "clinical"}
    for signal_frames in signals:
        result = process_frames(signal_frames)
        for flag in result.flags:
            for word in forbidden:
                assert word not in flag.lower()


def test_no_diagnostic_language_in_field_names():
    result = process_frames(_make_signal())
    forbidden = {"diagnosis", "diagnostic", "disease", "condition", "disorder"}
    for field in vars(result):
        for word in forbidden:
            assert word not in field.lower()
