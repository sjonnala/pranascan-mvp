"""Tests for scan session API endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import TEST_USER_ID

GOOD_RESULT = {
    "hr_bpm": 72.0,
    "hrv_ms": 45.0,
    "respiratory_rate": 16.0,
    "voice_jitter_pct": 0.5,
    "voice_shimmer_pct": 2.0,
    "quality_score": 0.92,
    "lighting_score": 0.8,
    "motion_score": 0.98,
    "face_confidence": 0.95,
    "audio_snr_db": 25.0,
    "flags": [],
}

BAD_LIGHTING_RESULT = {
    **GOOD_RESULT,
    "lighting_score": 0.2,  # Below 0.4 threshold
}


async def _grant_consent(client: AsyncClient, user_id: str = TEST_USER_ID):
    await client.post(
        "/api/v1/consent",
        json={"user_id": user_id, "consent_version": "1.0", "purpose": "wellness_screening"},
    )


async def _create_session(client: AsyncClient, user_id: str = TEST_USER_ID) -> str:
    resp = await client.post("/api/v1/scans/sessions", json={"user_id": user_id})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_session_requires_consent(client: AsyncClient):
    """Session creation fails without active consent."""
    resp = await client.post("/api/v1/scans/sessions", json={"user_id": TEST_USER_ID})
    assert resp.status_code == 403
    assert "consent" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_session_with_consent(client: AsyncClient):
    """Session creation succeeds with active consent."""
    await _grant_consent(client)
    resp = await client.post(
        "/api/v1/scans/sessions",
        json={"user_id": TEST_USER_ID, "device_model": "Pixel 8", "app_version": "0.1.0"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["user_id"] == TEST_USER_ID
    assert data["status"] == "initiated"
    assert data["device_model"] == "Pixel 8"


@pytest.mark.asyncio
async def test_complete_session_good_quality(client: AsyncClient):
    """Completing a session with good quality returns wellness indicators."""
    await _grant_consent(client)
    session_id = await _create_session(client)

    resp = await client.put(f"/api/v1/scans/sessions/{session_id}/complete", json=GOOD_RESULT)
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id
    assert data["hr_bpm"] == 72.0
    assert data["quality_score"] == 0.92
    assert data["trend_alert"] is None  # No prior baseline
    assert "diagnosis" not in str(data).lower()


@pytest.mark.asyncio
async def test_complete_session_bad_lighting_rejected(client: AsyncClient):
    """Session with poor lighting is rejected by quality gate."""
    await _grant_consent(client)
    session_id = await _create_session(client)

    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete", json=BAD_LIGHTING_RESULT
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "low_lighting" in detail["flags"]
    assert "diagnosis" not in str(resp.json()).lower()


@pytest.mark.asyncio
async def test_complete_session_not_found(client: AsyncClient):
    """Completing a non-existent session returns 404."""
    resp = await client.put(
        "/api/v1/scans/sessions/nonexistent-id/complete", json=GOOD_RESULT
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_session(client: AsyncClient):
    """GET session returns session with result after completion."""
    await _grant_consent(client)
    session_id = await _create_session(client)
    await client.put(f"/api/v1/scans/sessions/{session_id}/complete", json=GOOD_RESULT)

    resp = await client.get(f"/api/v1/scans/sessions/{session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session"]["id"] == session_id
    assert data["session"]["status"] == "completed"
    assert data["result"]["hr_bpm"] == 72.0


@pytest.mark.asyncio
async def test_scan_history_pagination(client: AsyncClient):
    """Scan history returns paginated completed sessions."""
    await _grant_consent(client)

    # Create and complete 3 sessions
    for _ in range(3):
        session_id = await _create_session(client)
        await client.put(f"/api/v1/scans/sessions/{session_id}/complete", json=GOOD_RESULT)

    resp = await client.get(
        "/api/v1/scans/history", params={"user_id": TEST_USER_ID, "page": 1, "page_size": 2}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_no_diagnostic_language_in_trend_alert(client: AsyncClient):
    """Trend alert values must not contain diagnostic language."""
    await _grant_consent(client)
    session_id = await _create_session(client)
    resp = await client.put(f"/api/v1/scans/sessions/{session_id}/complete", json=GOOD_RESULT)
    assert resp.status_code == 200
    data = resp.json()
    # trend_alert can only be null or "consider_lab_followup"
    assert data["trend_alert"] in (None, "consider_lab_followup")
    assert "diagnosis" not in str(data).lower()
    assert "diagnostic" not in str(data).lower()
