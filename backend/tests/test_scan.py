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


async def _grant_consent(client: AsyncClient, auth_headers: dict, user_id: str = TEST_USER_ID):
    await client.post(
        "/api/v1/consent",
        json={"user_id": user_id, "consent_version": "1.0", "purpose": "wellness_screening"},
        headers=auth_headers,
    )


async def _create_session(
    client: AsyncClient,
    auth_headers: dict,
    user_id: str = TEST_USER_ID,
) -> str:
    resp = await client.post(
        "/api/v1/scans/sessions",
        json={"user_id": user_id},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_session_requires_auth(client: AsyncClient):
    """Session creation fails without auth token."""
    resp = await client.post("/api/v1/scans/sessions", json={"user_id": TEST_USER_ID})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_session_requires_consent(client: AsyncClient, auth_headers: dict):
    """Session creation fails without active consent."""
    resp = await client.post(
        "/api/v1/scans/sessions",
        json={"user_id": TEST_USER_ID},
        headers=auth_headers,
    )
    assert resp.status_code == 403
    assert "consent" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_session_with_consent(client: AsyncClient, auth_headers: dict):
    """Session creation succeeds with valid auth + active consent."""
    await _grant_consent(client, auth_headers)
    resp = await client.post(
        "/api/v1/scans/sessions",
        json={"user_id": TEST_USER_ID, "device_model": "Pixel 8", "app_version": "0.1.0"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["user_id"] == TEST_USER_ID
    assert data["status"] == "initiated"
    assert data["device_model"] == "Pixel 8"


@pytest.mark.asyncio
async def test_complete_session_good_quality(client: AsyncClient, auth_headers: dict):
    """Completing a session with good quality returns wellness indicators."""
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=GOOD_RESULT,
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id
    assert data["hr_bpm"] == 72.0
    assert data["quality_score"] == 0.92
    assert data["trend_alert"] is None  # No prior baseline
    assert "diagnosis" not in str(data).lower()


@pytest.mark.asyncio
async def test_complete_session_bad_lighting_rejected(client: AsyncClient, auth_headers: dict):
    """Session with poor lighting is rejected by quality gate."""
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=BAD_LIGHTING_RESULT,
        headers=auth_headers,
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "low_lighting" in detail["flags"]
    assert "diagnosis" not in str(resp.json()).lower()


@pytest.mark.asyncio
async def test_complete_session_not_found(client: AsyncClient, auth_headers: dict):
    """Completing a non-existent session returns 404."""
    resp = await client.put(
        "/api/v1/scans/sessions/nonexistent-id/complete",
        json=GOOD_RESULT,
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_complete_session_other_user_forbidden(
    client: AsyncClient, auth_headers: dict, auth_headers_user2: dict
):
    """User cannot complete another user's session."""
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    # user2 tries to complete user1's session
    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=GOOD_RESULT,
        headers=auth_headers_user2,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_session(client: AsyncClient, auth_headers: dict):
    """GET session returns session with result after completion."""
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)
    await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=GOOD_RESULT,
        headers=auth_headers,
    )

    resp = await client.get(
        f"/api/v1/scans/sessions/{session_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session"]["id"] == session_id
    assert data["session"]["status"] == "completed"
    assert data["result"]["hr_bpm"] == 72.0


@pytest.mark.asyncio
async def test_get_session_requires_auth(client: AsyncClient, auth_headers: dict):
    """GET session requires auth."""
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    resp = await client.get(f"/api/v1/scans/sessions/{session_id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_scan_history_pagination(client: AsyncClient, auth_headers: dict):
    """Scan history returns paginated completed sessions for the authed user."""
    await _grant_consent(client, auth_headers)

    # Create and complete 3 sessions
    for _ in range(3):
        session_id = await _create_session(client, auth_headers)
        await client.put(
            f"/api/v1/scans/sessions/{session_id}/complete",
            json=GOOD_RESULT,
            headers=auth_headers,
        )

    resp = await client.get(
        "/api/v1/scans/history",
        params={"page": 1, "page_size": 2},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_no_diagnostic_language_in_trend_alert(client: AsyncClient, auth_headers: dict):
    """Trend alert values must not contain diagnostic language."""
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)
    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=GOOD_RESULT,
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    # trend_alert can only be null or "consider_lab_followup"
    assert data["trend_alert"] in (None, "consider_lab_followup")
    assert "diagnosis" not in str(data).lower()
    assert "diagnostic" not in str(data).lower()
