"""Unit tests for rPPG processor."""

import math

import numpy as np

from app.services.rppg_processor import FrameSample, RppgResult, build_frame_samples, process_frames

SAMPLE_RATE = 30  # fps
DURATION_S = 30


def _make_synthetic_signal(
    hr_bpm: float = 60.0,
    noise_std: float = 0.5,
    n_frames: int = SAMPLE_RATE * DURATION_S,
    fps: float = float(SAMPLE_RATE),
) -> list[FrameSample]:
    """
    Build a synthetic frame sequence with a green-channel pulsatile signal
    at the given HR in bpm. Background ~ 100 ADU, pulse amplitude ~ 5 ADU.
    """
    t = np.arange(n_frames) / fps  # seconds
    freq = hr_bpm / 60.0  # Hz
    # Green channel: DC baseline + pulsatile signal + noise
    g = 100.0 + 5.0 * np.sin(2.0 * math.pi * freq * t) + np.random.default_rng(42).normal(0, noise_std, n_frames)
    r = 80.0 + np.random.default_rng(1).normal(0, noise_std, n_frames)
    b = 60.0 + np.random.default_rng(2).normal(0, noise_std, n_frames)

    return [
        FrameSample(t_ms=float(t[i] * 1000), r_mean=float(r[i]), g_mean=float(g[i]), b_mean=float(b[i]))
        for i in range(n_frames)
    ]


# ---------------------------------------------------------------------------
# Basic functionality
# ---------------------------------------------------------------------------


def test_process_frames_returns_rppg_result():
    frames = _make_synthetic_signal(hr_bpm=72.0)
    result = process_frames(frames)
    assert isinstance(result, RppgResult)


def test_synthetic_60bpm_hr_within_tolerance():
    """A 60 bpm synthetic signal should produce HR within ±10 bpm."""
    frames = _make_synthetic_signal(hr_bpm=60.0, noise_std=0.2)
    result = process_frames(frames)
    assert result.hr_bpm is not None, f"No HR computed. Flags: {result.flags}"
    assert abs(result.hr_bpm - 60.0) <= 10.0, f"HR={result.hr_bpm} too far from 60 bpm"


def test_synthetic_80bpm_hr_within_tolerance():
    """An 80 bpm synthetic signal should produce HR within ±10 bpm."""
    frames = _make_synthetic_signal(hr_bpm=80.0, noise_std=0.2)
    result = process_frames(frames)
    assert result.hr_bpm is not None, f"No HR computed. Flags: {result.flags}"
    assert abs(result.hr_bpm - 80.0) <= 10.0, f"HR={result.hr_bpm} too far from 80 bpm"


def test_hr_bpm_in_physiological_range():
    """HR must be in [30, 220] bpm for any valid signal."""
    frames = _make_synthetic_signal(hr_bpm=72.0)
    result = process_frames(frames)
    if result.hr_bpm is not None:
        assert 30.0 <= result.hr_bpm <= 220.0


def test_hrv_ms_is_nonnegative():
    """HRV (RMSSD) must be ≥ 0."""
    frames = _make_synthetic_signal(hr_bpm=70.0)
    result = process_frames(frames)
    if result.hrv_ms is not None:
        assert result.hrv_ms >= 0.0


def test_quality_score_between_zero_and_one():
    """quality_score must be in [0, 1]."""
    frames = _make_synthetic_signal(hr_bpm=72.0)
    result = process_frames(frames)
    assert 0.0 <= result.quality_score <= 1.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_too_few_frames_returns_none_values():
    """Fewer than MIN_FRAMES frames returns None wellness values and flag."""
    frames = _make_synthetic_signal(n_frames=10)
    result = process_frames(frames)
    assert result.hr_bpm is None
    assert result.hrv_ms is None
    assert "insufficient_frames" in result.flags


def test_flat_signal_returns_none_values():
    """A flat (constant) green channel returns None values with flat_signal flag."""
    frames = [
        FrameSample(t_ms=float(i * 33), r_mean=80.0, g_mean=100.0, b_mean=60.0)
        for i in range(300)
    ]
    result = process_frames(frames)
    assert result.hr_bpm is None
    assert "flat_signal" in result.flags


def test_empty_frames_returns_insufficient_flag():
    result = process_frames([])
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


# ---------------------------------------------------------------------------
# No diagnostic language in output
# ---------------------------------------------------------------------------


def test_no_diagnostic_language_in_flags():
    """rPPG flags must not contain diagnostic language."""
    frames = _make_synthetic_signal(hr_bpm=72.0)
    result = process_frames(frames)
    forbidden = {"diagnosis", "diagnostic", "disease", "condition", "disorder"}
    for flag in result.flags:
        for word in forbidden:
            assert word not in flag.lower(), f"Diagnostic language '{word}' found in flag '{flag}'"
