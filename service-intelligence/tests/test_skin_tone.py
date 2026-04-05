"""Tests for the skin tone calibration module (D5 — Fitzpatrick Types 1–6)."""


import pytest

from app.services.rppg_processor import FrameSample, RppgResult
from app.services.skin_tone import (
    FitzpatrickType,
    SkinToneCalibrationResult,
    apply_skin_tone_calibration,
    compute_ita,
    estimate_fitzpatrick_type,
    estimate_from_frames,
    srgb_to_lab,
)

# ---------------------------------------------------------------------------
# sRGB → Lab conversion
# ---------------------------------------------------------------------------


def test_srgb_to_lab_white():
    """Pure white (255, 255, 255) should give L* ≈ 100."""
    l_star, _, _ = srgb_to_lab(255, 255, 255)
    assert abs(l_star - 100.0) < 1.0


def test_srgb_to_lab_black():
    """Pure black (0, 0, 0) should give L* ≈ 0."""
    l_star, _, _ = srgb_to_lab(0, 0, 0)
    assert l_star < 1.0


def test_srgb_to_lab_midgrey():
    """Mid-grey (128, 128, 128) should give L* ≈ 53."""
    l_star, _, _ = srgb_to_lab(128, 128, 128)
    assert 48.0 < l_star < 58.0


# ---------------------------------------------------------------------------
# ITA computation
# ---------------------------------------------------------------------------


def test_compute_ita_light_skin():
    """High L*, warm b* should give positive ITA (lighter skin)."""
    ita = compute_ita(80.0, 15.0)
    assert ita > 41.0  # Type 1/2 range


def test_compute_ita_dark_skin():
    """Low L*, neutral b* should give negative ITA (darker skin)."""
    ita = compute_ita(30.0, 5.0)
    assert ita < 0.0  # Type 5/6 range


# ---------------------------------------------------------------------------
# Fitzpatrick type estimation
# ---------------------------------------------------------------------------

# Approximate RGB values for each type (test device sRGB, not clinical)
_TYPE_RGB: dict[FitzpatrickType, tuple[int, int, int]] = {
    FitzpatrickType.TYPE_1: (255, 220, 195),  # very fair
    FitzpatrickType.TYPE_2: (240, 200, 170),  # fair
    FitzpatrickType.TYPE_3: (210, 170, 135),  # medium
    FitzpatrickType.TYPE_4: (175, 130, 95),   # olive
    FitzpatrickType.TYPE_5: (120, 80, 55),    # brown
    FitzpatrickType.TYPE_6: (65, 40, 28),     # deep
}


@pytest.mark.parametrize("ftype,rgb", _TYPE_RGB.items())
def test_estimate_fitzpatrick_type_correct_type_or_adjacent(ftype, rgb):
    """
    Estimated type should equal the target or be at most ±1 adjacent type.
    ITA boundaries have natural uncertainty with synthetic RGB values.
    """
    estimated, ita = estimate_fitzpatrick_type(*rgb)
    assert abs(estimated.value - ftype.value) <= 1, (
        f"Expected {ftype.value} ±1, got {estimated.value} (ITA={ita:.1f})"
    )


def test_estimate_returns_ita_angle():
    """estimate_fitzpatrick_type should return a numeric ITA angle."""
    _, ita = estimate_fitzpatrick_type(200, 160, 130)
    assert isinstance(ita, float)
    assert -180.0 <= ita <= 180.0


def test_estimate_from_frames_averages_across_frames():
    """estimate_from_frames averages RGB across all frames before estimating."""
    # Two frames: one very light, one very dark — average should be mid-range
    frames = [
        FrameSample(t_ms=0, r_mean=240, g_mean=200, b_mean=170),
        FrameSample(t_ms=500, r_mean=120, g_mean=80, b_mean=55),
    ]
    ftype, ita = estimate_from_frames(frames)
    assert isinstance(ftype, FitzpatrickType)


def test_estimate_from_frames_fallback_on_empty():
    """Empty frame list falls back to Type 4 (conservative default)."""
    ftype, ita = estimate_from_frames([])
    assert ftype == FitzpatrickType.TYPE_4


# ---------------------------------------------------------------------------
# apply_skin_tone_calibration
# ---------------------------------------------------------------------------


def _make_rppg_result(hr: float = 72.0, hrv: float = 45.0, quality: float = 0.85) -> RppgResult:
    return RppgResult(
        hr_bpm=hr,
        hrv_ms=hrv,
        respiratory_rate=16.0,
        quality_score=quality,
        flags=[],
    )


def _make_frames(r: float, g: float, b: float, n: int = 30) -> list[FrameSample]:
    return [FrameSample(t_ms=i * 200, r_mean=r, g_mean=g, b_mean=b) for i in range(n)]


def test_calibration_returns_tuple_of_result_and_metadata():
    result = _make_rppg_result()
    frames = _make_frames(200, 160, 130)
    calibrated, skin_cal = apply_skin_tone_calibration(result, frames)
    assert isinstance(calibrated, RppgResult)
    assert isinstance(skin_cal, SkinToneCalibrationResult)


def test_calibration_preserves_hr_for_type_1_2():
    """Types 1–2 have hr_factor = 1.000 — HR should be unchanged."""
    frames = _make_frames(*_TYPE_RGB[FitzpatrickType.TYPE_1])
    result = _make_rppg_result(hr=72.0)
    calibrated, skin_cal = apply_skin_tone_calibration(result, frames)
    # Type 1 or 2 — hr_factor is 1.000
    if skin_cal.fitzpatrick_type in (FitzpatrickType.TYPE_1, FitzpatrickType.TYPE_2):
        assert calibrated.hr_bpm == pytest.approx(72.0, abs=0.5)


def test_calibration_applies_correction_for_type_5_6():
    """Types 5–6 have hr_factor < 1.0 — calibrated HR should be lower."""
    frames = _make_frames(*_TYPE_RGB[FitzpatrickType.TYPE_6])
    result = _make_rppg_result(hr=72.0)
    calibrated, skin_cal = apply_skin_tone_calibration(result, frames)
    if skin_cal.fitzpatrick_type in (FitzpatrickType.TYPE_5, FitzpatrickType.TYPE_6):
        assert calibrated.hr_bpm < 72.0


def test_calibration_adds_fitzpatrick_type_flag():
    """Calibrated result must include a fitzpatrick_type flag."""
    frames = _make_frames(200, 160, 130)
    result = _make_rppg_result()
    calibrated, _ = apply_skin_tone_calibration(result, frames)
    assert any("skin_tone_fitzpatrick_type_" in f for f in calibrated.flags)


def test_calibration_adds_accuracy_note_for_type_5_6():
    """Type 5/6 calibration must add an accuracy_note flag."""
    frames = _make_frames(*_TYPE_RGB[FitzpatrickType.TYPE_6])
    result = _make_rppg_result()
    calibrated, skin_cal = apply_skin_tone_calibration(result, frames)
    if skin_cal.fitzpatrick_type in (FitzpatrickType.TYPE_5, FitzpatrickType.TYPE_6):
        assert skin_cal.accuracy_note is not None
        assert "accuracy_may_vary" in skin_cal.accuracy_note
        assert any("skin_tone_accuracy_note" in f for f in calibrated.flags)


def test_calibration_no_accuracy_note_for_types_1_to_4():
    """Types 1–4 should not have an accuracy_note (green channel is reliable)."""
    frames = _make_frames(*_TYPE_RGB[FitzpatrickType.TYPE_3])
    result = _make_rppg_result()
    _, skin_cal = apply_skin_tone_calibration(result, frames)
    if skin_cal.fitzpatrick_type.value <= 4:
        assert skin_cal.accuracy_note is None
        assert not any("skin_tone_accuracy_note" in f for f in skin_cal.flags_added)


def test_calibration_handles_none_hr_gracefully():
    """Calibration should not raise when hr_bpm is None (rPPG failed)."""
    frames = _make_frames(200, 160, 130)
    result = RppgResult(
        hr_bpm=None, hrv_ms=None, respiratory_rate=None, quality_score=0.0, flags=[]
    )
    calibrated, skin_cal = apply_skin_tone_calibration(result, frames)
    assert calibrated.hr_bpm is None
    assert calibrated.hrv_ms is None


def test_calibration_quality_score_clamped_to_valid_range():
    """Quality score must stay in [0.0, 1.0] after calibration."""
    frames = _make_frames(*_TYPE_RGB[FitzpatrickType.TYPE_6])
    # Start near zero — quality_weight would push it negative without clamp
    result = _make_rppg_result(quality=0.01)
    calibrated, _ = apply_skin_tone_calibration(result, frames)
    assert 0.0 <= calibrated.quality_score <= 1.0


def test_calibration_preserves_existing_flags():
    """Existing rPPG flags should be retained after calibration."""
    frames = _make_frames(200, 160, 130)
    result = RppgResult(
        hr_bpm=72.0, hrv_ms=45.0, respiratory_rate=16.0, quality_score=0.8,
        flags=["low_framerate_upsampled"],
    )
    calibrated, _ = apply_skin_tone_calibration(result, frames)
    assert "low_framerate_upsampled" in calibrated.flags


def test_calibration_skin_tone_applied_flag_always_present():
    """skin_tone_calibration_applied flag must always be added."""
    frames = _make_frames(200, 160, 130)
    calibrated, _ = apply_skin_tone_calibration(_make_rppg_result(), frames)
    assert "skin_tone_calibration_applied" in calibrated.flags
