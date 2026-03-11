"""Tests for post-scan feedback endpoints."""

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


async def _grant_consent(client: AsyncClient, auth_headers: dict, user_id: str = TEST_USER_ID):
    await client.post(
        "/api/v1/consent",
        json={"user_id": user_id, "consent_version": "1.0", "purpose": "wellness_screening"},
        headers=auth_headers,
    )


async def _create_session(
    client: AsyncClient, auth_headers: dict, user_id: str = TEST_USER_ID
) -> str:
    resp = await client.post(
        "/api/v1/scans/sessions",
        json={"user_id": user_id},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_completed_session(
    client: AsyncClient, auth_headers: dict, user_id: str = TEST_USER_ID
) -> str:
    await _grant_consent(client, auth_headers, user_id)
    session_id = await _create_session(client, auth_headers, user_id)
    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=GOOD_RESULT,
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return session_id


@pytest.mark.asyncio
async def test_create_feedback_for_completed_session(client: AsyncClient, auth_headers: dict):
    session_id = await _create_completed_session(client, auth_headers)

    resp = await client.post(
        "/api/v1/feedback",
        json={
            "session_id": session_id,
            "useful_response": "useful",
            "nps_score": 9,
            "comment": "Quick and clear.",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["session_id"] == session_id
    assert data["useful_response"] == "useful"
    assert data["nps_score"] == 9
    assert data["comment"] == "Quick and clear."


@pytest.mark.asyncio
async def test_create_feedback_trims_blank_comment(client: AsyncClient, auth_headers: dict):
    session_id = await _create_completed_session(client, auth_headers)

    resp = await client.post(
        "/api/v1/feedback",
        json={
            "session_id": session_id,
            "useful_response": "needs_work",
            "nps_score": 4,
            "comment": "   ",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["comment"] is None


@pytest.mark.asyncio
async def test_create_feedback_requires_completed_session(client: AsyncClient, auth_headers: dict):
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    resp = await client.post(
        "/api/v1/feedback",
        json={"session_id": session_id, "useful_response": "useful", "nps_score": 8},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "completed scan sessions" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_feedback_only_once_per_session(client: AsyncClient, auth_headers: dict):
    session_id = await _create_completed_session(client, auth_headers)

    first = await client.post(
        "/api/v1/feedback",
        json={"session_id": session_id, "useful_response": "useful", "nps_score": 8},
        headers=auth_headers,
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/api/v1/feedback",
        json={"session_id": session_id, "useful_response": "needs_work", "nps_score": 3},
        headers=auth_headers,
    )
    assert second.status_code == 409
    assert "already been recorded" in second.json()["detail"]


@pytest.mark.asyncio
async def test_get_feedback_for_session(client: AsyncClient, auth_headers: dict):
    session_id = await _create_completed_session(client, auth_headers)
    create = await client.post(
        "/api/v1/feedback",
        json={"session_id": session_id, "useful_response": "useful", "nps_score": 10},
        headers=auth_headers,
    )
    assert create.status_code == 201, create.text

    resp = await client.get(f"/api/v1/feedback/sessions/{session_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["session_id"] == session_id
    assert resp.json()["nps_score"] == 10


@pytest.mark.asyncio
async def test_get_feedback_returns_404_when_missing(client: AsyncClient, auth_headers: dict):
    session_id = await _create_completed_session(client, auth_headers)

    resp = await client.get(f"/api/v1/feedback/sessions/{session_id}", headers=auth_headers)
    assert resp.status_code == 404
    assert "No feedback found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_feedback_session_lookup_hidden_from_other_user(
    client: AsyncClient, auth_headers: dict, auth_headers_user2: dict
):
    session_id = await _create_completed_session(client, auth_headers)

    resp = await client.get(f"/api/v1/feedback/sessions/{session_id}", headers=auth_headers_user2)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_feedback_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/feedback",
        json={"session_id": "session-1", "useful_response": "useful", "nps_score": 8},
    )
    assert resp.status_code in (401, 403)
