"""
Tests for the quality gate service — D26 severity tiers.

Covers:
  - Hard failures (ERROR) still reject the scan
  - Borderline zones (WARNING) allow scan to proceed with flags
  - partial_occlusion_suspected for borderline face_confidence
  - warnings field populated correctly
  - motion_score has no warning zone (always hard gate)
  - All four metric dimensions
  - No diagnostic language in rejection messages
"""

from app.config import settings
from app.schemas.scan import ScanResultSubmit
from app.services.quality_gate import (
    _AUDIO_WARNING_DELTA,
    _FACE_WARNING_DELTA,
    _LIGHTING_WARNING_DELTA,
    run_quality_gate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE = {
    "scan_type": "standard",
    "hr_bpm": 72.0,
    "hrv_ms": 45.0,
    "respiratory_rate": 16.0,
    "voice_jitter_pct": 0.5,
    "voice_shimmer_pct": 2.0,
    "quality_score": 0.92,
    "lighting_score": 0.85,
    "motion_score": 0.98,
    "face_confidence": 0.95,
    "audio_snr_db": 25.0,
    "flags": [],
}


def _make(overrides: dict) -> ScanResultSubmit:
    return ScanResultSubmit(**{**_BASE, **overrides})


def _below_hard(threshold: float, delta: float) -> float:
    """Value that is clearly in the ERROR zone (below hard limit)."""
    return round(threshold - delta - 0.05, 3)


def _in_warning(threshold: float, delta: float) -> float:
    """Value that sits in the WARNING zone just below the threshold."""
    return round(threshold - delta / 2, 3)


# ---------------------------------------------------------------------------
# Baseline — good scan still passes
# ---------------------------------------------------------------------------


def test_good_scan_passes():
    result = run_quality_gate(_make({}))
    assert result.passed is True
    assert result.rejection_reason is None
    assert result.warnings == []


# ---------------------------------------------------------------------------
# Lighting — severity tiers
# ---------------------------------------------------------------------------


def test_lighting_hard_failure_rejects():
    """lighting below hard limit → scan rejected."""
    low = _below_hard(settings.min_lighting_score, _LIGHTING_WARNING_DELTA)
    result = run_quality_gate(_make({"lighting_score": low}))
    assert result.passed is False
    assert "low_lighting" in result.flags
    assert result.rejection_reason is not None


def test_lighting_borderline_proceeds_with_warning_flag():
    """lighting in warning zone → scan passes, borderline_lighting flag set."""
    borderline = _in_warning(settings.min_lighting_score, _LIGHTING_WARNING_DELTA)
    result = run_quality_gate(_make({"lighting_score": borderline}))
    assert result.passed is True
    assert "borderline_lighting" in result.flags
    assert "borderline_lighting" in result.warnings
    assert result.rejection_reason is None


def test_lighting_good_no_flags():
    result = run_quality_gate(_make({"lighting_score": settings.min_lighting_score + 0.2}))
    assert result.passed is True
    assert "low_lighting" not in result.flags
    assert "borderline_lighting" not in result.flags


# ---------------------------------------------------------------------------
# Motion — always hard gate (no warning zone)
# ---------------------------------------------------------------------------


def test_motion_failure_rejects():
    result = run_quality_gate(_make({"motion_score": 0.80}))
    assert result.passed is False
    assert "motion_detected" in result.flags


def test_motion_just_below_threshold_rejects_without_warning():
    """Motion has no warning zone — 0.94 is still a hard reject."""
    result = run_quality_gate(_make({"motion_score": 0.94}))
    assert result.passed is False
    assert "motion_detected" in result.flags
    assert "motion_detected" not in result.warnings


def test_motion_at_threshold_passes():
    result = run_quality_gate(_make({"motion_score": settings.min_motion_score}))
    assert result.passed is True


# ---------------------------------------------------------------------------
# Face confidence — severity tiers + partial occlusion flag
# ---------------------------------------------------------------------------


def test_face_confidence_hard_failure_rejects():
    """Face confidence clearly below hard limit → rejected."""
    low = _below_hard(settings.min_face_confidence, _FACE_WARNING_DELTA)
    result = run_quality_gate(_make({"face_confidence": low}))
    assert result.passed is False
    assert "face_not_detected" in result.flags
    assert result.rejection_reason is not None


def test_face_confidence_borderline_proceeds_with_partial_occlusion_flag():
    """Borderline face confidence → scan passes with partial_occlusion_suspected."""
    borderline = _in_warning(settings.min_face_confidence, _FACE_WARNING_DELTA)
    result = run_quality_gate(_make({"face_confidence": borderline}))
    assert result.passed is True
    assert "partial_occlusion_suspected" in result.flags
    assert "partial_occlusion_suspected" in result.warnings
    assert result.rejection_reason is None


def test_face_confidence_good_no_occlusion_flag():
    result = run_quality_gate(_make({"face_confidence": 0.95}))
    assert result.passed is True
    assert "partial_occlusion_suspected" not in result.flags
    assert "face_not_detected" not in result.flags


def test_glasses_user_borderline_face_passes():
    """
    Realistic glasses scenario: face_confidence slightly below gate (0.76).
    Should proceed — user with glasses shouldn't be hard-rejected.
    """
    result = run_quality_gate(_make({"face_confidence": 0.76}))
    assert result.passed is True
    assert "partial_occlusion_suspected" in result.flags


# ---------------------------------------------------------------------------
# Audio SNR — severity tiers
# ---------------------------------------------------------------------------


def test_audio_snr_hard_failure_rejects():
    low = _below_hard(settings.min_audio_snr_db, _AUDIO_WARNING_DELTA)
    result = run_quality_gate(_make({"audio_snr_db": low}))
    assert result.passed is False
    assert "high_noise" in result.flags


def test_audio_snr_borderline_proceeds_with_warning():
    borderline = _in_warning(settings.min_audio_snr_db, _AUDIO_WARNING_DELTA)
    result = run_quality_gate(_make({"audio_snr_db": borderline}))
    assert result.passed is True
    assert "borderline_noise" in result.flags
    assert "borderline_noise" in result.warnings


def test_audio_snr_good_no_flags():
    result = run_quality_gate(_make({"audio_snr_db": 30.0}))
    assert result.passed is True
    assert "high_noise" not in result.flags
    assert "borderline_noise" not in result.flags


# ---------------------------------------------------------------------------
# Multiple simultaneous warnings — all allowed to accumulate
# ---------------------------------------------------------------------------


def test_multiple_warnings_all_pass():
    """Borderline lighting + borderline face → both warnings, scan still passes."""
    borderline_lighting = _in_warning(settings.min_lighting_score, _LIGHTING_WARNING_DELTA)
    borderline_face = _in_warning(settings.min_face_confidence, _FACE_WARNING_DELTA)
    result = run_quality_gate(
        _make({"lighting_score": borderline_lighting, "face_confidence": borderline_face})
    )
    assert result.passed is True
    assert "borderline_lighting" in result.warnings
    assert "partial_occlusion_suspected" in result.warnings
    assert len(result.warnings) == 2


def test_warning_and_error_together_rejects():
    """One warning + one error → scan rejected (error wins)."""
    borderline_lighting = _in_warning(settings.min_lighting_score, _LIGHTING_WARNING_DELTA)
    result = run_quality_gate(
        _make({"lighting_score": borderline_lighting, "motion_score": 0.80})
    )
    assert result.passed is False
    assert "borderline_lighting" in result.flags
    assert "motion_detected" in result.flags
    assert result.warnings == ["borderline_lighting"]


def test_deep_dive_ignores_face_and_audio_gates():
    result = run_quality_gate(
        _make(
            {
                "scan_type": "deep_dive",
                "face_confidence": 0.0,
                "audio_snr_db": 0.0,
                "lighting_score": 0.9,
                "motion_score": 0.99,
            }
        )
    )
    assert result.passed is False
    assert "poor_thumb_contact" in result.flags
    assert "high_noise" not in result.flags
    assert "face_not_detected" not in result.flags


def test_deep_dive_passes_with_good_contact_and_no_audio():
    result = run_quality_gate(
        _make(
            {
                "scan_type": "deep_dive",
                "face_confidence": 0.92,
                "audio_snr_db": 0.0,
                "lighting_score": 0.92,
                "motion_score": 0.99,
            }
        )
    )
    assert result.passed is True
    assert result.warnings == []


# ---------------------------------------------------------------------------
# QualityGateResult structure
# ---------------------------------------------------------------------------


def test_passed_result_has_empty_warnings_by_default():
    result = run_quality_gate(_make({}))
    assert isinstance(result.warnings, list)
    assert result.warnings == []


def test_warnings_field_is_subset_of_flags():
    """Every warning flag must also appear in the full flags list."""
    borderline_face = _in_warning(settings.min_face_confidence, _FACE_WARNING_DELTA)
    result = run_quality_gate(_make({"face_confidence": borderline_face}))
    for warning in result.warnings:
        assert warning in result.flags


def test_existing_payload_flags_preserved():
    """Flags already in the payload must not be dropped."""
    result = run_quality_gate(_make({"flags": ["partial_scan"]}))
    assert "partial_scan" in result.flags


# ---------------------------------------------------------------------------
# No diagnostic language in rejection messages
# ---------------------------------------------------------------------------


def test_no_diagnostic_language_in_rejection_reason():
    """Rejection messages must never contain diagnostic language."""
    low_light = _below_hard(settings.min_lighting_score, _LIGHTING_WARNING_DELTA)
    result = run_quality_gate(_make({"lighting_score": low_light}))
    diagnostic_terms = ["diagnos", "disease", "disorder", "illness", "syndrome"]
    reason = (result.rejection_reason or "").lower()
    for term in diagnostic_terms:
        assert term not in reason, f"Diagnostic term '{term}' found in rejection reason"


def test_no_diagnostic_language_in_flags():
    result = run_quality_gate(_make({"lighting_score": 0.1, "motion_score": 0.5}))
    diagnostic_terms = ["diagnos", "disease", "disorder", "illness", "syndrome"]
    for flag in result.flags:
        for term in diagnostic_terms:
            assert term not in flag.lower()
