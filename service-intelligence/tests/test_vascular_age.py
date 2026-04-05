"""Tests for vascular age heuristic (v1)."""

import pytest

from app.services.vascular_age import estimate_vascular_age

# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_returns_null_when_no_metrics():
    result = estimate_vascular_age(None, None)
    assert result.estimate_years is None
    assert result.confidence is None
    assert result.used_hrv is False


def test_young_profile_maps_to_low_age_bracket():
    result = estimate_vascular_age(hr_bpm=62.0, hrv_ms=55.0)
    assert result.estimate_years == 25.0


def test_older_profile_maps_to_higher_age_bracket():
    result = estimate_vascular_age(hr_bpm=75.0, hrv_ms=15.0)
    assert result.estimate_years == 75.0


def test_middle_profile_reasonable_range():
    result = estimate_vascular_age(hr_bpm=68.0, hrv_ms=35.0)
    assert result.estimate_years is not None
    assert 35.0 <= result.estimate_years <= 55.0


def test_confidence_is_bounded_0_to_1():
    for hr, hrv in [(62.0, 55.0), (75.0, 15.0), (68.0, 35.0), (50.0, 100.0)]:
        result = estimate_vascular_age(hr_bpm=hr, hrv_ms=hrv)
        assert result.confidence is not None
        assert 0.0 <= result.confidence <= 1.0


def test_hr_only_works_when_hrv_missing():
    result = estimate_vascular_age(hr_bpm=68.0, hrv_ms=None)
    assert result.estimate_years is not None
    assert result.used_hrv is False


def test_hrv_only_works_when_hr_missing():
    result = estimate_vascular_age(hr_bpm=None, hrv_ms=55.0)
    assert result.estimate_years is not None
    assert result.used_hrv is True


def test_out_of_range_hr_returns_null():
    result = estimate_vascular_age(hr_bpm=5.0, hrv_ms=None)
    assert result.estimate_years is None
