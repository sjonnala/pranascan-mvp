"""Phase 0 voice safety tests: abstention, accuracy and service-layer propagation.

Fixtures are synthetic with exact ground truth (tests/voice_fixtures.py). Bug IDs refer
to the Cycle-1 voice budget-phone audit (B1-B19).
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from app.schemas.scan import ScanResultSubmit
from app.services import voice_processor
from app.services.scan_evaluation_service import (
    _apply_server_side_voice_dsp,
    evaluate_scan_submission,
)
from app.services.voice_processor import (
    REASON_CLIPPING,
    REASON_NO_VOICE,
    REASON_SHORT_VOICE,
    SAMPLE_RATE,
    process_audio,
)
from tests.voice_fixtures import (
    at_dbfs,
    budget_agc_hi,
    ceiling_fan_hi,
    harmonic_tone,
    mix_at_snr,
    mixer_grinder_hi,
    quiet_vowel,
    room_floor_hi,
    sustained_vowel_hi,
    to_client,
)

JITTER_TOLERANCE_PP = 0.3  # audit acceptance band for local jitter (percentage points)

# ---------------------------------------------------------------------------
# Accuracy on harmonic vowels with known ground truth (B3, B4, B5, B10)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("seed", "f0_hz", "jitter_pct"),
    [
        (1, 110.0, 0.5),
        (2, 150.0, 0.8),
        (3, 210.0, 1.0),
        (4, 240.0, 0.4),
        (5, 130.0, 1.4),
    ],
)
def test_quiet_room_vowel_jitter_within_tolerance(seed: int, f0_hz: float, jitter_pct: float):
    samples, truth = quiet_vowel(seed, f0_hz=f0_hz, jitter_pct=jitter_pct)

    result = process_audio(samples)

    assert result.jitter_pct is not None, result.flags
    assert (
        abs(result.jitter_pct - truth.jitter_local_pct) <= JITTER_TOLERANCE_PP
    ), f"jitter {result.jitter_pct} vs truth {truth.jitter_local_pct:.3f}"
    assert result.f0_hz is not None
    assert abs(result.f0_hz - truth.f0_hz) / truth.f0_hz < 0.05


def test_harmonics_do_not_double_count_glottal_cycles():
    """B3: the old bandpass peak picker counted 2-3 peaks per cycle and reported >10 %."""
    samples, truth = quiet_vowel(11, f0_hz=120.0, jitter_pct=0.6)

    result = process_audio(samples)

    assert result.jitter_pct is not None
    assert result.jitter_pct < 2.0
    assert abs(result.f0_hz - truth.f0_hz) / truth.f0_hz < 0.05


def test_slow_intonation_is_not_reported_as_jitter():
    """B4: std/mean jitter counts ±4 % intonation drift; local jitter must not."""
    samples, truth = quiet_vowel(12, f0_hz=160.0, jitter_pct=0.5, drift_pct=4.0)
    assert truth.jitter_std_over_mean_pct > 2.0  # what the old definition would chase

    result = process_audio(samples)

    assert result.jitter_pct is not None
    assert abs(result.jitter_pct - truth.jitter_local_pct) <= JITTER_TOLERANCE_PP


def test_higher_jitter_reads_higher():
    low, _ = quiet_vowel(21, f0_hz=140.0, jitter_pct=0.4)
    high, _ = quiet_vowel(21, f0_hz=140.0, jitter_pct=2.0)

    low_result, high_result = process_audio(low), process_audio(high)

    assert low_result.jitter_pct is not None and high_result.jitter_pct is not None
    assert high_result.jitter_pct > low_result.jitter_pct + 0.8


@pytest.mark.parametrize(("seed", "f0_hz"), [(201, 200.0), (202, 120.0), (207, 120.0)])
def test_quiet_room_shimmer_is_close_to_truth(seed: int, f0_hz: float):
    samples, truth = quiet_vowel(seed, f0_hz=f0_hz, jitter_pct=0.3, shimmer_pct=3.0)

    result = process_audio(samples)

    assert result.shimmer_pct is not None, result.flags
    assert abs(result.shimmer_pct - truth.shimmer_local_pct) <= 1.5


def test_low_hnr_withholds_shimmer_but_keeps_jitter_with_flag():
    """B12: additive noise inflates shimmer, so it is withheld (explicitly) below 12 dB HNR."""
    samples, truth = quiet_vowel(31, f0_hz=150.0, jitter_pct=0.6, shimmer_pct=3.0)

    result = process_audio(samples)

    assert result.hnr_db is not None and result.hnr_db < 12.0
    assert result.shimmer_pct is None
    assert "shimmer_withheld_low_hnr" in result.flags
    assert result.jitter_pct is not None
    assert abs(result.jitter_pct - truth.jitter_local_pct) <= JITTER_TOLERANCE_PP


def test_vowel_under_ceiling_fan_is_measured_with_real_snr():
    """B1/B2: fan noise must not fake voicing nor produce the 40 dB sentinel."""
    voice, truth = sustained_vowel_hi(41, f0_hz=180.0, jitter_pct=0.8)
    mixed = mix_at_snr(voice, ceiling_fan_hi(41), 20.0, truth)

    result = process_audio(to_client(mixed))

    assert result.snr_db != 40.0
    assert result.jitter_pct is not None, result.flags
    assert abs(result.jitter_pct - truth.jitter_local_pct) <= 0.5
    assert result.snr_db is not None
    assert 10.0 <= result.snr_db <= 30.0


def test_two_separate_vowels_are_not_spliced():
    """B9: runs are tracked separately; a splice must not create a period jump."""
    first, truth_a = sustained_vowel_hi(
        51, f0_hz=150.0, jitter_pct=0.6, onset_s=0.3, duration_s=1.8
    )
    second, truth_b = sustained_vowel_hi(
        52, f0_hz=150.0, jitter_pct=0.6, onset_s=2.7, duration_s=1.8
    )
    floor = at_dbfs(room_floor_hi(53), -55.0)

    result = process_audio(to_client(first + second + floor))

    assert result.jitter_pct is not None, result.flags
    expected = (truth_a.jitter_local_pct + truth_b.jitter_local_pct) / 2.0
    assert abs(result.jitter_pct - expected) <= JITTER_TOLERANCE_PP


# ---------------------------------------------------------------------------
# No-voice negatives: the processor must say "no voice" (B1, B2, B13, B14)
# ---------------------------------------------------------------------------


def test_digital_silence_abstains():
    result = process_audio([0.0] * (5 * SAMPLE_RATE))

    assert result.jitter_pct is None and result.shimmer_pct is None
    assert result.abstention_reason == REASON_NO_VOICE
    assert result.snr_db is None


@pytest.mark.parametrize("seed", [61, 62, 63])
def test_ceiling_fan_only_abstains(seed: int):
    noise = at_dbfs(ceiling_fan_hi(seed), -32.0)

    result = process_audio(to_client(noise))

    assert result.jitter_pct is None, result.flags
    assert result.shimmer_pct is None
    assert result.snr_db != 40.0
    assert result.abstained


@pytest.mark.parametrize("seed", [71, 72, 73])
def test_mixer_grinder_only_abstains(seed: int):
    noise = at_dbfs(mixer_grinder_hi(seed), -26.0)

    result = process_audio(to_client(noise))

    assert result.jitter_pct is None, result.flags
    assert result.snr_db != 40.0


@pytest.mark.parametrize("seed", [81, 82])
def test_agc_lifted_quiet_fan_abstains(seed: int):
    """A -50 dBFS fan lifted by a budget-phone AGC is loud, but it is not a voice."""
    noise = budget_agc_hi(at_dbfs(ceiling_fan_hi(seed), -50.0))

    result = process_audio(to_client(noise))

    assert result.jitter_pct is None, result.flags


def test_quiet_room_floor_only_abstains():
    result = process_audio(to_client(at_dbfs(room_floor_hi(91), -55.0)))

    assert result.jitter_pct is None
    assert result.abstention_reason == REASON_NO_VOICE


@pytest.mark.parametrize("f0_hz", [100.0, 150.0, 200.0])
def test_mains_locked_stationary_tone_is_rejected(f0_hz: float):
    """B14: a perfectly steady tone on a 50 Hz multiple is machinery, not a voice."""
    result = process_audio(harmonic_tone(f0_hz))

    assert result.jitter_pct is None
    assert "stationary_tone_suspected" in result.flags


def test_clipped_vowel_abstains_with_clip_fraction():
    """B13: > 1 % of samples at full scale -> explicit abstention."""
    voice, _ = sustained_vowel_hi(101, f0_hz=160.0, jitter_pct=0.8)
    clipped = np.clip(voice * 10 ** (20.0 / 20.0), -1.0, 1.0)

    result = process_audio(to_client(clipped))

    assert result.jitter_pct is None
    assert result.abstention_reason == REASON_CLIPPING
    assert any(flag.startswith("clip_fraction:") for flag in result.flags)


def test_short_vowel_abstains_with_duration_reason():
    samples, _ = quiet_vowel(111, f0_hz=150.0, onset_s=1.0, duration_s=0.6)

    result = process_audio(samples)

    assert result.jitter_pct is None
    assert result.abstention_reason == REASON_SHORT_VOICE


def test_continuous_voice_with_no_pause_reports_no_snr_sentinel():
    """B2: with no unvoiced frames there is no noise reference -> None, never 40 dB."""
    samples, _ = quiet_vowel(121, f0_hz=170.0, onset_s=0.0, duration_s=5.0)

    result = process_audio(samples)

    assert result.snr_db is None
    assert "no_noise_reference" in result.flags
    assert result.jitter_pct is not None


def test_abstention_always_carries_a_reason():
    for samples in (
        [0.0] * (5 * SAMPLE_RATE),
        to_client(at_dbfs(ceiling_fan_hi(131), -32.0)),
        [0.1] * 100,
    ):
        result = process_audio(samples)
        assert result.jitter_pct is None
        assert result.abstention_reason is not None
        assert result.abstention_reason in result.flags


# ---------------------------------------------------------------------------
# Implementation hygiene (B15, B18)
# ---------------------------------------------------------------------------


def test_processor_uses_second_order_sections_not_ba_filtfilt(monkeypatch):
    """B15: numerically safe filtering; the (b, a) filtfilt path must not be used."""

    def _forbidden(*_args, **_kwargs):
        raise AssertionError("signal.filtfilt (b, a form) must not be used")

    monkeypatch.setattr(voice_processor.signal, "filtfilt", _forbidden)
    samples, _ = quiet_vowel(141, f0_hz=150.0)

    assert process_audio(samples).jitter_pct is not None


def test_privacy_docstring_no_longer_claims_samples_are_non_identifying():
    """B18: the waveform carries pitch, formants and timbre."""
    doc = inspect.getdoc(voice_processor) or ""

    assert "no identifiable voice characteristics" not in doc
    assert "speaker identification" in doc


# ---------------------------------------------------------------------------
# Service layer: flags propagate and abstention clears client scalars (B7, B8)
# ---------------------------------------------------------------------------


def _submission(**overrides) -> ScanResultSubmit:
    base = {
        "quality_score": 0.9,
        "lighting_score": 0.8,
        "motion_score": 0.98,
        "face_confidence": 0.95,
        "audio_snr_db": 24.0,
        "voice_jitter_pct": 1.1,
        "voice_shimmer_pct": 4.2,
    }
    return ScanResultSubmit(**{**base, **overrides})


def test_server_abstention_clears_unverified_client_voice_values():
    noise = to_client(at_dbfs(ceiling_fan_hi(151), -32.0))

    processed, flags = _apply_server_side_voice_dsp(_submission(audio_samples=noise))

    assert processed.voice_jitter_pct is None
    assert processed.voice_shimmer_pct is None
    assert processed.audio_snr_db == 24.0  # client SNR untouched, never a sentinel
    assert "voice_abstained" in flags
    assert "voice_client_values_cleared" in flags


def test_server_abstention_on_silence_clears_client_values():
    processed, flags = _apply_server_side_voice_dsp(
        _submission(audio_samples=[0.0] * (5 * SAMPLE_RATE))
    )

    assert processed.voice_jitter_pct is None
    assert processed.voice_shimmer_pct is None
    assert f"voice_{REASON_NO_VOICE}" in flags


def test_voice_processor_flags_are_propagated_with_prefix():
    samples, _ = quiet_vowel(161, f0_hz=170.0, onset_s=0.0, duration_s=5.0)

    _processed, flags = _apply_server_side_voice_dsp(_submission(audio_samples=samples))

    assert "voice_no_noise_reference" in flags


def test_server_measurement_replaces_client_values():
    samples, truth = quiet_vowel(171, f0_hz=150.0, jitter_pct=0.7)

    processed, flags = _apply_server_side_voice_dsp(_submission(audio_samples=samples))

    assert processed.voice_jitter_pct is not None
    assert processed.voice_jitter_pct != 1.1
    assert abs(processed.voice_jitter_pct - truth.jitter_local_pct) <= JITTER_TOLERANCE_PP
    assert processed.audio_snr_db is not None and processed.audio_snr_db != 40.0
    assert "voice_abstained" not in flags


def test_missing_server_snr_keeps_client_snr():
    samples, _ = quiet_vowel(181, f0_hz=170.0, onset_s=0.0, duration_s=5.0)

    processed, _flags = _apply_server_side_voice_dsp(_submission(audio_samples=samples))

    assert processed.voice_jitter_pct is not None
    assert processed.audio_snr_db == 24.0


def test_no_audio_samples_leaves_client_values_and_adds_no_flags():
    submission = _submission()

    processed, flags = _apply_server_side_voice_dsp(submission)

    assert processed == submission
    assert flags == []


def test_evaluation_flags_include_voice_flags_end_to_end():
    noise = to_client(at_dbfs(mixer_grinder_hi(191), -26.0))

    evaluation = evaluate_scan_submission(_submission(audio_samples=noise))

    assert "voice_abstained" in evaluation.flags
    assert evaluation.submission.voice_jitter_pct is None
    assert evaluation.submission.voice_shimmer_pct is None
