"""Tests for vascular age heuristic (v1)."""

import pytest
from httpx import AsyncClient

from app.services.vascular_age import estimate_vascular_age
from tests.conftest import TEST_USER_ID

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


# ---------------------------------------------------------------------------
# Integration test (router)
# ---------------------------------------------------------------------------

GOOD_SCAN_PAYLOAD = {
    "hr_bpm": 65.0,
    "hrv_ms": 45.0,
    "respiratory_rate": 15.0,
    "quality_score": 0.92,
    "lighting_score": 0.85,
    "motion_score": 0.98,
    "face_confidence": 0.95,
    "audio_snr_db": 25.0,
    "flags": [],
}


async def _grant_consent(client: AsyncClient, auth_headers: dict):
    await client.post(
        "/api/v1/consent",
        json={"user_id": TEST_USER_ID, "consent_version": "1.0", "purpose": "wellness_screening"},
        headers=auth_headers,
    )


async def _create_session(client: AsyncClient, auth_headers: dict) -> str:
    resp = await client.post(
        "/api/v1/scans/sessions",
        json={"user_id": TEST_USER_ID},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_scan_result_includes_vascular_age(client: AsyncClient, auth_headers: dict):
    """Integration: scan response includes non-null vascular age fields."""
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=GOOD_SCAN_PAYLOAD,
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "vascular_age_estimate" in data, "Missing vascular_age_estimate in response"
    assert "vascular_age_confidence" in data, "Missing vascular_age_confidence in response"
    assert data["vascular_age_estimate"] is not None, "vascular_age_estimate should not be null"
    assert data["vascular_age_confidence"] is not None, "vascular_age_confidence should not be null"
    assert 0.0 <= data["vascular_age_confidence"] <= 1.0
