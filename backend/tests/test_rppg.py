"""
Unit tests for rPPG processor (app/services/rppg_processor.py).

Signal generation strategy:
  All synthetic signals use a fixed RNG seed so tests are deterministic.
  The green channel carries a sinusoidal pulse at the target HR frequency,
  matching real face rPPG physiology (pulsatile blood volume change).
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

# ---------------------------------------------------------------------------
# Signal generators
# ---------------------------------------------------------------------------

RNG = np.random.default_rng(42)


def _make_signal(
    hr_bpm: float = 72.0,
    fps: float = 30.0,
    duration_s: float = 30.0,
    noise_std: float = 0.3,
    amplitude: float = 5.0,
    seed: int = 42,
) -> list[FrameSample]:
    """
    Build a synthetic FrameSample sequence with a pulsatile green signal.

    Parameters
    ----------
    hr_bpm     : Target heart rate in beats per minute.
    fps        : Frames per second (camera capture rate).
    duration_s : Recording duration in seconds.
    noise_std  : Gaussian noise standard deviation (ADU).
    amplitude  : Pulse amplitude in ADU (green channel peak-to-peak / 2).
    seed       : RNG seed for reproducibility.
    """
    rng = np.random.default_rng(seed)
    n = int(fps * duration_s)
    t = np.arange(n) / fps
    freq = hr_bpm / 60.0  # Hz

    g = 100.0 + amplitude * np.sin(2.0 * math.pi * freq * t) + rng.normal(0, noise_std, n)
    r = 80.0 + rng.normal(0, noise_std, n)
    b = 60.0 + rng.normal(0, noise_std, n)

    return [
        FrameSample(t_ms=float(t[i] * 1000), r_mean=float(r[i]),
                    g_mean=float(g[i]), b_mean=float(b[i]))
        for i in range(n)
    ]


def _make_2fps_signal(
    hr_bpm: float = 55.0,
    duration_s: float = 30.0,
    noise_std: float = 0.3,
) -> list[FrameSample]:
    """2 fps signal (realistic mobile JPEG-capture rate)."""
    return _make_signal(hr_bpm=hr_bpm, fps=2.0, duration_s=duration_s, noise_std=noise_std)


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Accuracy — 30 fps signals
# ---------------------------------------------------------------------------


def test_60bpm_at_30fps_within_tolerance():
    """60 bpm synthetic signal → HR within ±8 bpm."""
    result = process_frames(_make_signal(hr_bpm=60.0, fps=30.0, noise_std=0.2))
    assert result.hr_bpm is not None, f"No HR. Flags: {result.flags}"
    assert abs(result.hr_bpm - 60.0) <= 8.0, f"HR={result.hr_bpm} bpm, expected ~60"


def test_80bpm_at_30fps_within_tolerance():
    result = process_frames(_make_signal(hr_bpm=80.0, fps=30.0, noise_std=0.2))
    assert result.hr_bpm is not None, f"No HR. Flags: {result.flags}"
    assert abs(result.hr_bpm - 80.0) <= 8.0, f"HR={result.hr_bpm} bpm, expected ~80"


def test_100bpm_at_30fps_within_tolerance():
    result = process_frames(_make_signal(hr_bpm=100.0, fps=30.0, noise_std=0.2))
    assert result.hr_bpm is not None, f"No HR. Flags: {result.flags}"
    assert abs(result.hr_bpm - 100.0) <= 12.0, f"HR={result.hr_bpm} bpm, expected ~100"


# ---------------------------------------------------------------------------
# Accuracy — 2 fps signals (mobile JPEG-proxy capture rate)
# ---------------------------------------------------------------------------


def test_55bpm_at_2fps_upsampled_and_detected():
    """
    2 fps signal at 55 bpm.
    Processor upsamples to 10 fps → full cardiac band available.
    Adds 'low_framerate_upsampled' flag; HR within ±10 bpm.
    """
    result = process_frames(_make_2fps_signal(hr_bpm=55.0, duration_s=30.0, noise_std=0.15))
    assert "low_framerate_upsampled" in result.flags
    assert result.hr_bpm is not None, f"No HR. Flags: {result.flags}"
    assert abs(result.hr_bpm - 55.0) <= 10.0, f"HR={result.hr_bpm} bpm, expected ~55"


def test_72bpm_at_2fps_aliasing_documented():
    """
    At 2 fps (Nyquist = 1 Hz = 60 bpm), 72 bpm aliases to |1.2 - 2| = 0.8 Hz = 48 bpm.
    Linear interpolation cannot un-alias a sub-Nyquist signal.

    Acceptance: processor must not crash, and must flag low_framerate_upsampled.
    HR accuracy at > 60 bpm requires ≥ 4 fps capture (Sprint 3 target).
    The detected value may be the aliased frequency (~48 bpm) or None.
    """
    result = process_frames(_make_2fps_signal(hr_bpm=72.0, duration_s=30.0, noise_std=0.15))
    assert "low_framerate_upsampled" in result.flags
    # Processor must return a result without crashing
    assert isinstance(result, RppgResult)
    # If a value is returned it must be in physiological range (even if aliased)
    if result.hr_bpm is not None:
        assert 30.0 <= result.hr_bpm <= 220.0


# ---------------------------------------------------------------------------
# Bounds checking
# ---------------------------------------------------------------------------


def test_hr_always_in_physiological_range():
    """Any returned hr_bpm must be in [30, 220] bpm."""
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
        assert 0.0 <= result.quality_score <= 1.0, f"quality_score={result.quality_score}"


# ---------------------------------------------------------------------------
# Noisy signal degradation
# ---------------------------------------------------------------------------


def test_high_noise_does_not_crash():
    """Very noisy signal (std ≈ 30 ADU) must return a result, not raise."""
    result = process_frames(_make_signal(hr_bpm=72.0, noise_std=30.0))
    assert isinstance(result, RppgResult)


def test_high_noise_degrades_quality():
    """Noisy signal quality score should be lower than clean signal."""
    clean = process_frames(_make_signal(hr_bpm=72.0, noise_std=0.1))
    noisy = process_frames(_make_signal(hr_bpm=72.0, noise_std=20.0))
    # Allow noisy to produce a result but expect lower quality
    assert noisy.quality_score <= clean.quality_score + 0.1


# ---------------------------------------------------------------------------
# Input validation — edge cases
# ---------------------------------------------------------------------------


def test_empty_frames_returns_insufficient_frames():
    result = process_frames([])
    assert result.hr_bpm is None
    assert "insufficient_frames" in result.flags
    assert result.quality_score == 0.0


def test_too_few_frames_returns_insufficient_frames():
    frames = _make_signal(fps=30.0, duration_s=0.5)  # 15 frames
    result = process_frames(frames)
    assert result.hr_bpm is None
    assert "insufficient_frames" in result.flags


def test_insufficient_temporal_span():
    """30 frames in 2 seconds → below MIN_TEMPORAL_SPAN_S (8s)."""
    frames = [
        FrameSample(t_ms=float(i * 33), r_mean=80.0,
                    g_mean=100.0 + 5.0 * math.sin(2 * math.pi * 1.2 * i * 0.033),
                    b_mean=60.0)
        for i in range(30)
    ]
    result = process_frames(frames)
    assert result.hr_bpm is None
    assert "insufficient_temporal_span" in result.flags


def test_flat_signal_returns_flag():
    """Constant green channel → flat_signal flag, no HR."""
    frames = [
        FrameSample(t_ms=float(i * 33), r_mean=80.0, g_mean=100.0, b_mean=60.0)
        for i in range(300)
    ]
    result = process_frames(frames)
    assert result.hr_bpm is None
    assert "flat_signal" in result.flags


def test_non_monotonic_timestamps_returns_flag():
    """Timestamps that go backwards (> 1 reversal) → irregular_timestamps."""
    frames = _make_signal(hr_bpm=72.0, fps=30.0, duration_s=15.0)
    # Reverse timestamps for half the frames — severe non-monotonicity
    bad = [
        FrameSample(
            t_ms=frames[i].t_ms if i % 2 == 0 else frames[max(0, i - 10)].t_ms,
            r_mean=frames[i].r_mean,
            g_mean=frames[i].g_mean,
            b_mean=frames[i].b_mean,
        )
        for i in range(len(frames))
    ]
    result = process_frames(bad)
    assert "irregular_timestamps" in result.flags
    assert result.hr_bpm is None


def test_single_frame_returns_insufficient():
    result = process_frames([FrameSample(t_ms=0.0, r_mean=80.0, g_mean=100.0, b_mean=60.0)])
    assert result.hr_bpm is None
    assert "insufficient_frames" in result.flags


# ---------------------------------------------------------------------------
# build_frame_samples helper
# ---------------------------------------------------------------------------


def test_build_frame_samples_converts_dicts():
    raw = [{"t_ms": 0.0, "r_mean": 80.0, "g_mean": 100.0, "b_mean": 60.0}]
    frames = build_frame_samples(raw)
    assert len(frames) == 1
    assert frames[0].t_ms == 0.0
    assert frames[0].g_mean == 100.0


def test_build_frame_samples_handles_multiple():
    raw = [
        {"t_ms": float(i * 33), "r_mean": 80.0, "g_mean": 100.0, "b_mean": 60.0}
        for i in range(100)
    ]
    frames = build_frame_samples(raw)
    assert len(frames) == 100
    assert frames[-1].t_ms == pytest.approx(99 * 33.0)


# ---------------------------------------------------------------------------
# No diagnostic language
# ---------------------------------------------------------------------------


def test_no_diagnostic_language_in_flags():
    """All processor flags must be free of diagnostic terminology."""
    signals = [
        _make_signal(hr_bpm=72.0),
        _make_signal(noise_std=20.0),
        [],
        _make_2fps_signal(),
    ]
    forbidden = {"diagnosis", "diagnostic", "disease", "condition", "disorder", "clinical"}
    for sig in signals:
        result = process_frames(sig)
        for flag in result.flags:
            for word in forbidden:
                assert word not in flag.lower(), \
                    f"Diagnostic term '{word}' found in flag '{flag}'"


def test_no_diagnostic_language_in_field_names():
    """RppgResult field names must not contain diagnostic terms."""
    result = process_frames(_make_signal())
    forbidden = {"diagnosis", "diagnostic", "disease", "condition", "disorder"}
    for field in vars(result):
        for word in forbidden:
            assert word not in field.lower()
