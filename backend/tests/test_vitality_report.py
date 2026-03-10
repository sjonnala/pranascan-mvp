"""Tests for the Weekly Vitality Report endpoints."""

import pytest
from httpx import AsyncClient

from app.services.vitality_report import DISCLAIMER
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


async def _complete_scan(
    client: AsyncClient,
    auth_headers: dict,
    result: dict | None = None,
    user_id: str = TEST_USER_ID,
) -> dict:
    """Create a session and complete it, returning the scan result JSON."""
    if result is None:
        result = GOOD_RESULT

    # Create session
    resp = await client.post(
        "/api/v1/scans/sessions",
        json={"user_id": user_id},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    session_id = resp.json()["id"]

    # Complete session
    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=result,
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_generate_report_with_no_scans(client: AsyncClient, auth_headers: dict):
    """POST /reports/generate for a new user with 0 scans → 201, scan_count=0, disclaimer present."""
    resp = await client.post("/api/v1/reports/generate", headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["scan_count"] == 0
    assert DISCLAIMER in data["summary_text"]


@pytest.mark.asyncio
async def test_generate_report_with_scans(client: AsyncClient, auth_headers: dict):
    """Submit 3 scans first, then generate report → scan_count=3, avg_hr_bpm not None."""
    await _grant_consent(client, auth_headers)
    for _ in range(3):
        await _complete_scan(client, auth_headers)

    resp = await client.post("/api/v1/reports/generate", headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["scan_count"] == 3
    assert data["avg_hr_bpm"] is not None
    assert data["avg_hr_bpm"] == pytest.approx(72.0, abs=0.1)


@pytest.mark.asyncio
async def test_generate_report_stores_in_db(client: AsyncClient, auth_headers: dict):
    """Generate twice — both should succeed (201). Each generates a new report."""
    resp1 = await client.post("/api/v1/reports/generate", headers=auth_headers)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/v1/reports/generate", headers=auth_headers)
    assert resp2.status_code == 201

    # Each call gets its own ID
    assert resp1.json()["id"] != resp2.json()["id"]


@pytest.mark.asyncio
async def test_get_latest_report_404_when_none(client: AsyncClient, auth_headers: dict):
    """GET /reports/latest for a user with no reports → 404."""
    resp = await client.get("/api/v1/reports/latest", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_latest_report_returns_most_recent(client: AsyncClient, auth_headers: dict):
    """Generate two reports, GET /reports/latest → returns the most recently generated one."""
    resp1 = await client.post("/api/v1/reports/generate", headers=auth_headers)
    assert resp1.status_code == 201
    id1 = resp1.json()["id"]

    resp2 = await client.post("/api/v1/reports/generate", headers=auth_headers)
    assert resp2.status_code == 201
    id2 = resp2.json()["id"]

    resp = await client.get("/api/v1/reports/latest", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == id2
    assert resp.json()["id"] != id1


@pytest.mark.asyncio
async def test_summary_text_contains_no_diagnostic_language(
    client: AsyncClient, auth_headers: dict
):
    """Verify summary_text avoids any diagnostic language."""
    resp = await client.post("/api/v1/reports/generate", headers=auth_headers)
    assert resp.status_code == 201
    text = resp.json()["summary_text"].lower()

    forbidden = ["diagnos", "disease", "disorder", "condition", "treatment"]
    for word in forbidden:
        assert word not in text, f"Diagnostic term '{word}' found in summary_text"


@pytest.mark.asyncio
async def test_summary_text_contains_disclaimer(client: AsyncClient, auth_headers: dict):
    """Verify the required disclaimer is present in every generated report."""
    resp = await client.post("/api/v1/reports/generate", headers=auth_headers)
    assert resp.status_code == 201
    assert DISCLAIMER in resp.json()["summary_text"]


@pytest.mark.asyncio
async def test_week_over_week_delta_none_when_no_prior_data(
    client: AsyncClient, auth_headers: dict
):
    """
    When there is no data from the prior week window, delta fields should be None.
    (Full prior-week population test would require DB timestamp patching.)
    """
    await _grant_consent(client, auth_headers)
    await _complete_scan(client, auth_headers)

    resp = await client.post("/api/v1/reports/generate", headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    # No prior-week data exists, so deltas should be None
    assert data["delta_hr_bpm"] is None
    assert data["delta_hrv_ms"] is None


@pytest.mark.asyncio
async def test_report_requires_auth(client: AsyncClient):
    """POST /reports/generate without auth header → 401 or 403."""
    resp = await client.post("/api/v1/reports/generate")
    assert resp.status_code in (401, 403)
