"""Unit tests for voice DSP processor.

Phase 0 (voice audit B16): assertions no longer sit behind ``if result.jitter_pct is not
None`` guards, so a test cannot pass just because the processor abstained. Realistic
harmonic-vowel and home-noise fixtures live in ``test_phase0_voice_fixes.py``.
"""

import math

import numpy as np

from app.services.voice_processor import (
    MIN_VOICED_FRACTION_ACCOMMODATED,
    REASON_SHORT_VOICE,
    SAMPLE_RATE,
    SNR_THRESHOLD_FOR_ACCOMMODATION_DB,
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


def test_pure_sine_jitter_near_zero():
    """A perfectly periodic (non-mains) sine has zero true jitter."""
    result = process_audio(_pure_sine(freq_hz=220.0))
    assert result.jitter_pct is not None, result.flags
    assert result.jitter_pct < 0.3, f"Jitter too high on pure sine: {result.jitter_pct}%"


def test_pure_sine_shimmer_near_zero():
    result = process_audio(_pure_sine(freq_hz=220.0))
    assert result.shimmer_pct is not None, result.flags
    assert result.shimmer_pct < 0.5, f"Shimmer too high on pure sine: {result.shimmer_pct}%"


def test_continuous_sine_has_no_snr_sentinel():
    """No pause means no noise reference: SNR is unknown (None), never a 40 dB sentinel."""
    result = process_audio(_pure_sine(freq_hz=220.0, amplitude=0.8))
    assert result.snr_db is None
    assert "no_noise_reference" in result.flags


def test_mains_multiple_pure_sine_is_treated_as_stationary_tone():
    """A perfectly steady 200 Hz tone (4 x 50 Hz) cannot be told from mains machinery."""
    result = process_audio(_pure_sine(freq_hz=200.0))
    assert result.jitter_pct is None
    assert "stationary_tone_suspected" in result.flags


def test_noisy_sine_has_higher_jitter_than_pure():
    """Additive noise perturbs cycle timing, so measured jitter rises."""
    pure_result = process_audio(_pure_sine(freq_hz=220.0))
    noisy_result = process_audio(_noisy_sine(freq_hz=220.0, amplitude=0.5, noise_std=0.1))
    assert pure_result.jitter_pct is not None
    assert noisy_result.jitter_pct is not None, noisy_result.flags
    assert noisy_result.jitter_pct > pure_result.jitter_pct


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
    assert result.abstained
    assert result.abstention_reason == "no_voice_detected"


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


def test_partial_voicing_low_snr_is_not_accommodated():
    """Low-SNR partial voicing must not use the accented-vowel accommodation path.

    The old version of this test used a constant DC offset as "noise"; DC is now removed
    before analysis, so real broadband noise is used instead.
    """
    clean = np.array(_partially_voiced_sine(voiced_duration_s=2.0, amplitude=0.05))
    noise = np.random.default_rng(7).normal(0.0, 0.01, len(clean))
    result = process_audio(list(clean + noise))

    assert result.snr_db is not None
    assert result.snr_db < 20.0
    assert "accented_vowel_accommodated" not in result.flags


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


# ---------------------------------------------------------------------------
# D26: Accented vowel accommodation
# ---------------------------------------------------------------------------


def _partial_voiced_high_snr(
    voiced_fraction: float = 0.40,
    freq_hz: float = 220.0,
    duration_s: float = 5.0,
) -> list[float]:
    """
    Synthetic recording where only `voiced_fraction` of frames are voiced
    but the voiced segment has high SNR (pure sine, no added noise).
    Remaining frames are silence (amplitude = 0).
    """
    total_samples = int(SAMPLE_RATE * duration_s)
    voiced_samples = int(total_samples * voiced_fraction)
    t = np.arange(voiced_samples) / float(SAMPLE_RATE)
    voiced_part = list(0.8 * np.sin(2.0 * math.pi * freq_hz * t))
    silence_part = [0.0] * (total_samples - voiced_samples)
    return voiced_part + silence_part


def test_accented_vowel_accommodated_when_voiced_fraction_low_snr_high():
    """
    voiced_fraction in [MIN_VOICED_FRACTION_ACCOMMODATED, 0.50) + high SNR
    → processor proceeds; 'accented_vowel_accommodated' flag added.
    """
    samples = _partial_voiced_high_snr(voiced_fraction=0.40)
    result = process_audio(samples)
    # The accommodation should trigger
    assert "accented_vowel_accommodated" in result.flags, (
        f"Expected accented_vowel_accommodated flag. Got flags: {result.flags}, "
        f"voiced_fraction={result.voiced_fraction:.2f}"
    )


def test_accented_vowel_insufficient_voiced_fraction_with_low_snr_rejected():
    """
    voiced_fraction in accommodation zone but SNR < threshold → NOT accommodated.
    The 'insufficient_voiced_content' flag should fire instead.
    """
    # Add noise to reduce SNR below threshold
    total = int(SAMPLE_RATE * 5.0)
    voiced = int(total * 0.40)
    t = np.arange(voiced) / float(SAMPLE_RATE)
    voiced_part = np.array(0.3 * np.sin(2.0 * math.pi * 220.0 * t))
    # High-amplitude noise throughout to tank SNR
    noise = np.random.default_rng(42).uniform(-0.3, 0.3, total)
    combined = list(voiced_part) + [0.0] * (total - voiced)
    noisy = [a + b for a, b in zip(combined, noise, strict=False)]
    result = process_audio(noisy)
    assert "accented_vowel_accommodated" not in result.flags


def test_standard_voiced_fraction_not_flagged_as_accented():
    """
    Full 5s voiced sine (voiced_fraction ≥ 0.80) should NOT get
    accented_vowel_accommodated flag.
    """
    result = process_audio(_pure_sine())
    assert "accented_vowel_accommodated" not in result.flags


def test_short_voiced_segment_still_rejected():
    """
    Less than 1 s of voice (here 15 % of a 5 s clip) is always rejected, even at
    high SNR, with an explicit duration reason.
    """
    samples = _partial_voiced_high_snr(voiced_fraction=0.15)
    result = process_audio(samples)
    assert result.jitter_pct is None
    assert result.shimmer_pct is None
    assert result.abstention_reason == REASON_SHORT_VOICE


def test_accommodation_constants_are_sensible():
    """Accommodation constants must be within expected engineering bounds."""
    assert 0.30 <= MIN_VOICED_FRACTION_ACCOMMODATED < 0.50
    assert 15.0 <= SNR_THRESHOLD_FOR_ACCOMMODATION_DB <= 30.0
