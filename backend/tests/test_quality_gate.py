"""Unit tests for the scan quality gate warning/error tiers."""

from app.schemas.scan import ScanResultSubmit
from app.services.quality_gate import run_quality_gate


def _payload(**overrides) -> ScanResultSubmit:
    data = {
        "quality_score": 0.92,
        "lighting_score": 0.80,
        "motion_score": 0.98,
        "face_confidence": 0.95,
        "audio_snr_db": 25.0,
        "flags": [],
    }
    data.update(overrides)
    return ScanResultSubmit(**data)


def test_borderline_lighting_is_warning_not_rejection():
    result = run_quality_gate(_payload(lighting_score=0.37))

    assert result.passed is True
    assert result.rejection_reason is None
    assert "borderline_lighting" in result.flags
    assert result.warnings == ["borderline_lighting"]


def test_borderline_face_confidence_sets_partial_occlusion_warning():
    result = run_quality_gate(_payload(face_confidence=0.75))

    assert result.passed is True
    assert result.rejection_reason is None
    assert "partial_occlusion_suspected" in result.flags
    assert result.warnings == ["partial_occlusion_suspected"]


def test_borderline_audio_snr_is_warning_not_rejection():
    result = run_quality_gate(_payload(audio_snr_db=12.0))

    assert result.passed is True
    assert result.rejection_reason is None
    assert "borderline_noise" in result.flags
    assert result.warnings == ["borderline_noise"]


def test_motion_remains_hard_failure_without_warning_zone():
    result = run_quality_gate(_payload(motion_score=0.90))

    assert result.passed is False
    assert result.warnings == []
    assert result.flags == ["motion_detected"]
    assert result.rejection_reason is not None
    assert "Hold still during the scan." in result.rejection_reason


def test_warning_flags_are_preserved_even_when_another_metric_hard_fails():
    result = run_quality_gate(_payload(lighting_score=0.37, motion_score=0.90))

    assert result.passed is False
    assert "borderline_lighting" in result.flags
    assert "motion_detected" in result.flags
    assert result.warnings == ["borderline_lighting"]
    assert result.rejection_reason is not None
    assert "Motion score" in result.rejection_reason
