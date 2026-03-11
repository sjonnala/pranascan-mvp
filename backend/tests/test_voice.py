"""Unit tests for voice DSP processor."""

import math

import numpy as np

from app.services.voice_processor import (
    SAMPLE_RATE,
    VoiceResult,
    build_audio_samples,
    process_audio,
)


def _pure_sine(
    freq_hz: float = 220.0, duration_s: float = 5.0, amplitude: float = 0.8
) -> list[float]:
    """Generate a pure sine wave at given frequency."""
    t = np.arange(int(SAMPLE_RATE * duration_s)) / float(SAMPLE_RATE)
    return list(amplitude * np.sin(2.0 * math.pi * freq_hz * t))


def _noisy_sine(
    freq_hz: float = 220.0,
    duration_s: float = 5.0,
    amplitude: float = 0.8,
    noise_std: float = 0.3,
) -> list[float]:
    """Generate a sine wave with additive Gaussian noise."""
    rng = np.random.default_rng(99)
    t = np.arange(int(SAMPLE_RATE * duration_s)) / float(SAMPLE_RATE)
    clean = amplitude * np.sin(2.0 * math.pi * freq_hz * t)
    noise = rng.normal(0, noise_std, len(t))
    return list(np.clip(clean + noise, -1.0, 1.0))


def _silence(duration_s: float = 5.0) -> list[float]:
    return [0.0] * int(SAMPLE_RATE * duration_s)


def _partially_voiced_sine(
    voiced_duration_s: float = 2.0,
    total_duration_s: float = 5.0,
    freq_hz: float = 220.0,
    amplitude: float = 0.8,
    silence_level: float = 0.0,
) -> list[float]:
    """Generate a clip with voiced content followed by low-energy silence."""
    voiced = _pure_sine(freq_hz=freq_hz, duration_s=voiced_duration_s, amplitude=amplitude)
    silence = [silence_level] * int(SAMPLE_RATE * max(total_duration_s - voiced_duration_s, 0.0))
    return voiced + silence


# ---------------------------------------------------------------------------
# Basic functionality
# ---------------------------------------------------------------------------


def test_process_audio_returns_voice_result():
    samples = _pure_sine()
    result = process_audio(samples)
    assert isinstance(result, VoiceResult)


def test_pure_sine_jitter_low():
    """Pure sine should have jitter < 5%."""
    samples = _pure_sine(freq_hz=200.0)
    result = process_audio(samples)
    if result.jitter_pct is not None:
        assert result.jitter_pct < 5.0, f"Jitter too high on pure sine: {result.jitter_pct}%"


def test_pure_sine_shimmer_low():
    """Pure sine should have shimmer < 5%."""
    samples = _pure_sine(freq_hz=200.0)
    result = process_audio(samples)
    if result.shimmer_pct is not None:
        assert result.shimmer_pct < 5.0, f"Shimmer too high on pure sine: {result.shimmer_pct}%"


def test_pure_sine_snr_high():
    """Pure sine (no silence frames) should yield high SNR or ~40dB."""
    samples = _pure_sine(freq_hz=200.0, amplitude=0.8)
    result = process_audio(samples)
    assert result.snr_db is not None
    assert result.snr_db > 15.0, f"SNR too low for pure sine: {result.snr_db} dB"


def test_noisy_sine_has_higher_jitter_than_pure():
    """Noisy sine should have higher jitter than pure sine."""
    pure_result = process_audio(_pure_sine(freq_hz=200.0))
    noisy_result = process_audio(_noisy_sine(freq_hz=200.0, noise_std=0.15))
    # Only compare if both produced valid results
    if pure_result.jitter_pct is not None and noisy_result.jitter_pct is not None:
        assert noisy_result.jitter_pct >= pure_result.jitter_pct


def test_voiced_fraction_high_for_continuous_sine():
    """Continuous sine should have voiced_fraction ≥ 0.8."""
    samples = _pure_sine()
    result = process_audio(samples)
    assert result.voiced_fraction >= 0.8


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_silence_returns_none_jitter():
    """Silent recording returns None for jitter/shimmer."""
    result = process_audio(_silence())
    assert result.jitter_pct is None
    assert result.shimmer_pct is None


def test_too_few_samples_returns_flag():
    """Very short recording returns insufficient_samples flag."""
    result = process_audio([0.1] * 100)
    assert "insufficient_samples" in result.flags
    assert result.jitter_pct is None


def test_voiced_fraction_low_for_silence():
    """Silence recording should have low voiced fraction."""
    result = process_audio(_silence())
    assert result.voiced_fraction < 0.2


def test_accented_vowel_accommodation_allows_high_snr_partial_voicing():
    """High-SNR clips with 35–50% voiced content should still be processed."""
    result = process_audio(_partially_voiced_sine(voiced_duration_s=2.0, amplitude=0.8))

    assert 0.35 <= result.voiced_fraction < 0.5
    assert result.snr_db is not None
    assert result.snr_db >= 20.0
    assert "accented_vowel_accommodated" in result.flags
    assert "insufficient_voiced_content" not in result.flags
    assert result.jitter_pct is not None
    assert result.shimmer_pct is not None


def test_partial_voicing_low_snr_still_returns_insufficient_voiced_content():
    """Low-SNR partial voicing must not use the accented-vowel accommodation path."""
    result = process_audio(
        _partially_voiced_sine(voiced_duration_s=2.0, amplitude=0.02, silence_level=0.005)
    )

    assert 0.35 <= result.voiced_fraction < 0.5
    assert result.snr_db is not None
    assert result.snr_db < 20.0
    assert "accented_vowel_accommodated" not in result.flags
    assert "insufficient_voiced_content" in result.flags
    assert result.jitter_pct is None
    assert result.shimmer_pct is None


# ---------------------------------------------------------------------------
# build_audio_samples helper
# ---------------------------------------------------------------------------


def test_build_audio_samples_clamps_values():
    """Values outside [-1.0, 1.0] are clamped."""
    raw = [2.0, -3.0, 0.5, -0.5]
    result = build_audio_samples(raw)
    assert result[0] == 1.0
    assert result[1] == -1.0
    assert result[2] == 0.5
    assert result[3] == -0.5


def test_build_audio_samples_converts_to_float():
    raw = [1, 0, -1]
    result = build_audio_samples(raw)
    assert all(isinstance(v, float) for v in result)


# ---------------------------------------------------------------------------
# No diagnostic language
# ---------------------------------------------------------------------------


def test_no_diagnostic_language_in_voice_flags():
    """Voice processor flags must not contain diagnostic language."""
    result = process_audio(_pure_sine())
    forbidden = {"diagnosis", "diagnostic", "disease", "condition", "disorder"}
    for flag in result.flags:
        for word in forbidden:
            assert word not in flag.lower(), f"Diagnostic word '{word}' in flag '{flag}'"
