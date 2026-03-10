"""
Tests for S2-06: ABHA adapter — link, status, unlink, sync, feature flag.

All tests run with abha_enabled=True, abha_sandbox=True (no real HTTP calls).
"""

from unittest.mock import patch

import pytest
from httpx import AsyncClient

from tests.conftest import (  # noqa: F401 (TEST_USER_ID_2 used in fixture params)
    TEST_USER_ID,
    TEST_USER_ID_2,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_ABHA_ID = "91-2345-6789-0123"
VALID_ABHA_RAW = "91234567890123"  # same, no hyphens
INVALID_ABHA_SHORT = "1234-5678"
INVALID_ABHA_ALPHA = "AB-CDEF-1234-5678"


def _abha_enabled_patch():
    """Patch settings so ABHA is enabled + sandbox for all tests."""
    return patch.multiple(
        "app.config.settings",
        abha_enabled=True,
        abha_sandbox=True,
    )


# ---------------------------------------------------------------------------
# POST /abha/link
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/abha/link", json={"abha_id": VALID_ABHA_ID})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_link_abha_account(client: AsyncClient, auth_headers: dict):
    with _abha_enabled_patch():
        resp = await client.post(
            "/api/v1/abha/link",
            json={"abha_id": VALID_ABHA_ID},
            headers=auth_headers,
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["user_id"] == TEST_USER_ID
    assert data["abha_id"] == VALID_ABHA_ID
    assert data["sandbox"] is True
    assert "linked_at" in data


@pytest.mark.asyncio
async def test_link_abha_normalises_raw_digits(client: AsyncClient, auth_headers: dict):
    """Raw 14-digit input should be normalised to hyphenated form."""
    with _abha_enabled_patch():
        resp = await client.post(
            "/api/v1/abha/link",
            json={"abha_id": VALID_ABHA_RAW},
            headers=auth_headers,
        )
    assert resp.status_code == 201
    assert resp.json()["abha_id"] == VALID_ABHA_ID


@pytest.mark.asyncio
async def test_link_abha_invalid_format_short(client: AsyncClient, auth_headers: dict):
    with _abha_enabled_patch():
        resp = await client.post(
            "/api/v1/abha/link",
            json={"abha_id": INVALID_ABHA_SHORT},
            headers=auth_headers,
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_link_abha_invalid_format_alpha(client: AsyncClient, auth_headers: dict):
    with _abha_enabled_patch():
        resp = await client.post(
            "/api/v1/abha/link",
            json={"abha_id": INVALID_ABHA_ALPHA},
            headers=auth_headers,
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_link_abha_replaces_existing(client: AsyncClient, auth_headers: dict):
    """Linking a second ABHA ID replaces the first (soft-delete)."""
    second_abha = "11-2222-3333-4444"
    with _abha_enabled_patch():
        await client.post(
            "/api/v1/abha/link", json={"abha_id": VALID_ABHA_ID}, headers=auth_headers
        )
        resp = await client.post(
            "/api/v1/abha/link", json={"abha_id": second_abha}, headers=auth_headers
        )
    assert resp.status_code == 201
    assert resp.json()["abha_id"] == second_abha


# ---------------------------------------------------------------------------
# GET /abha/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/abha/status")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_status_no_link(client: AsyncClient, auth_headers: dict):
    with _abha_enabled_patch():
        resp = await client.get("/api/v1/abha/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["linked"] is False
    assert data["abha_id"] is None
    assert data["user_id"] == TEST_USER_ID
    assert data["abha_enabled"] is True
    assert data["sandbox"] is True


@pytest.mark.asyncio
async def test_status_after_link(client: AsyncClient, auth_headers: dict):
    with _abha_enabled_patch():
        await client.post(
            "/api/v1/abha/link", json={"abha_id": VALID_ABHA_ID}, headers=auth_headers
        )
        resp = await client.get("/api/v1/abha/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["linked"] is True
    assert data["abha_id"] == VALID_ABHA_ID
    assert data["linked_at"] is not None


@pytest.mark.asyncio
async def test_status_reflects_disabled_flag(client: AsyncClient, auth_headers: dict):
    """When ABHA is disabled, status endpoint still works and shows abha_enabled=False."""
    with patch.multiple("app.config.settings", abha_enabled=False, abha_sandbox=True):
        resp = await client.get("/api/v1/abha/status", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["abha_enabled"] is False


# ---------------------------------------------------------------------------
# DELETE /abha/link
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unlink_requires_auth(client: AsyncClient):
    resp = await client.delete("/api/v1/abha/link")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unlink_no_existing_link(client: AsyncClient, auth_headers: dict):
    with _abha_enabled_patch():
        resp = await client.delete("/api/v1/abha/link", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unlink_clears_active_link(client: AsyncClient, auth_headers: dict):
    with _abha_enabled_patch():
        await client.post(
            "/api/v1/abha/link", json={"abha_id": VALID_ABHA_ID}, headers=auth_headers
        )
        resp = await client.delete("/api/v1/abha/link", headers=auth_headers)
        assert resp.status_code == 204

        # Verify status now shows unlinked
        status_resp = await client.get("/api/v1/abha/status", headers=auth_headers)
        assert status_resp.json()["linked"] is False


# ---------------------------------------------------------------------------
# POST /abha/sync/{session_id}
# ---------------------------------------------------------------------------


async def _create_completed_scan(client: AsyncClient, auth_headers: dict) -> str:
    """Helper: consent + create + complete a scan session, return session_id."""
    await client.post(
        "/api/v1/consent",
        json={"user_id": TEST_USER_ID, "consent_version": "1.0", "purpose": "wellness_screening"},
        headers=auth_headers,
    )
    create_resp = await client.post(
        "/api/v1/scans/sessions",
        json={"user_id": TEST_USER_ID, "device_model": "TestDevice", "app_version": "1.0"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["id"]

    complete_resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json={
            "hr_bpm": 72.0,
            "hrv_ms": 45.0,
            "respiratory_rate": 15.0,
            "quality_score": 0.92,
            "lighting_score": 0.85,
            "motion_score": 0.97,
            "face_confidence": 0.90,
            "audio_snr_db": 22.0,
            "voice_jitter_pct": 0.5,
            "voice_shimmer_pct": 1.2,
        },
        headers=auth_headers,
    )
    assert complete_resp.status_code == 200
    return session_id


@pytest.mark.asyncio
async def test_sync_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/abha/sync/some-session-id")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sync_session_not_found(client: AsyncClient, auth_headers: dict):
    with _abha_enabled_patch():
        resp = await client.post(
            "/api/v1/abha/sync/nonexistent-session", headers=auth_headers
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sync_skipped_disabled(client: AsyncClient, auth_headers: dict):
    """When ABHA disabled, sync returns skipped_disabled."""
    with patch.multiple("app.config.settings", abha_enabled=False, abha_sandbox=True):
        session_id = await _create_completed_scan(client, auth_headers)
        resp = await client.post(f"/api/v1/abha/sync/{session_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "skipped_disabled"
    assert data["abha_id"] is None


@pytest.mark.asyncio
async def test_sync_skipped_no_link(client: AsyncClient, auth_headers: dict):
    """Enabled but no ABHA link → skipped_no_link."""
    with _abha_enabled_patch():
        session_id = await _create_completed_scan(client, auth_headers)
        resp = await client.post(f"/api/v1/abha/sync/{session_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "skipped_no_link"
    assert data["abha_id"] is None


@pytest.mark.asyncio
async def test_sync_success_sandbox(client: AsyncClient, auth_headers: dict):
    """With ABHA enabled + sandbox + linked account → status=success + gateway_ref."""
    with _abha_enabled_patch():
        session_id = await _create_completed_scan(client, auth_headers)
        await client.post(
            "/api/v1/abha/link", json={"abha_id": VALID_ABHA_ID}, headers=auth_headers
        )
        resp = await client.post(f"/api/v1/abha/sync/{session_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["abha_id"] == VALID_ABHA_ID
    assert data["gateway_ref"] is not None
    assert data["gateway_ref"].startswith("SANDBOX-")
    assert data["sandbox"] is True
    assert data["session_id"] == session_id


@pytest.mark.asyncio
async def test_sync_status_shows_last_sync(client: AsyncClient, auth_headers: dict):
    """After sync, GET /abha/status should show last_sync_at and last_sync_status."""
    with _abha_enabled_patch():
        session_id = await _create_completed_scan(client, auth_headers)
        await client.post(
            "/api/v1/abha/link", json={"abha_id": VALID_ABHA_ID}, headers=auth_headers
        )
        await client.post(f"/api/v1/abha/sync/{session_id}", headers=auth_headers)
        status_resp = await client.get("/api/v1/abha/status", headers=auth_headers)

    data = status_resp.json()
    assert data["last_sync_at"] is not None
    assert data["last_sync_status"] == "success"


@pytest.mark.asyncio
async def test_sync_wrong_user_session(
    client: AsyncClient, auth_headers: dict, auth_headers_user2: dict
):
    """User 2 cannot sync a session owned by user 1."""
    with _abha_enabled_patch():
        session_id = await _create_completed_scan(client, auth_headers)
        resp = await client.post(
            f"/api/v1/abha/sync/{session_id}", headers=auth_headers_user2
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sync_incomplete_session_rejected(client: AsyncClient, auth_headers: dict):
    """Syncing an INITIATED (not completed) session returns 409."""
    await client.post(
        "/api/v1/consent",
        json={"user_id": TEST_USER_ID, "consent_version": "1.0", "purpose": "wellness_screening"},
        headers=auth_headers,
    )
    create_resp = await client.post(
        "/api/v1/scans/sessions",
        json={"user_id": TEST_USER_ID, "device_model": "TestDevice", "app_version": "1.0"},
        headers=auth_headers,
    )
    session_id = create_resp.json()["id"]

    with _abha_enabled_patch():
        await client.post(
            "/api/v1/abha/link", json={"abha_id": VALID_ABHA_ID}, headers=auth_headers
        )
        resp = await client.post(f"/api/v1/abha/sync/{session_id}", headers=auth_headers)
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Adapter unit tests (direct service calls)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_is_enabled_respects_flag():
    """is_enabled() reflects the settings flag."""
    with patch("app.config.settings.abha_enabled", False):
        from app.services import abha_adapter
        assert abha_adapter.is_enabled() is False

    with patch("app.config.settings.abha_enabled", True):
        assert abha_adapter.is_enabled() is True


@pytest.mark.asyncio
async def test_adapter_fhir_observations_built_correctly():
    """_build_fhir_observations skips None values, includes LOINC codes where applicable."""
    from app.services.abha_adapter import _build_fhir_observations

    vitals = {"hr_bpm": 72.0, "hrv_ms": None, "voice_jitter_pct": 0.5}
    entries = _build_fhir_observations("91-2345-6789-0123", "test-session", vitals)

    # Only non-None vitals should produce entries
    assert len(entries) == 2
    resource_types = [e["resource"]["resourceType"] for e in entries]
    assert all(rt == "Observation" for rt in resource_types)

    # HR entry should have LOINC code
    hr_entry = entries[0]
    assert hr_entry["resource"]["code"]["coding"][0]["code"] == "8867-4"
    assert hr_entry["resource"]["valueQuantity"]["value"] == 72.0

    # No-diagnostic-language disclaimer must be present
    for entry in entries:
        note = entry["resource"]["note"][0]["text"]
        assert "Not a diagnostic" in note
