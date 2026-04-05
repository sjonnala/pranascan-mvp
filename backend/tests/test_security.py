"""
Security and DPDP compliance checklist tests.

These tests verify:
  1. Security response headers are present on API responses
  2. Scan rate limit returns 429 when exceeded
  3. DPDP checklist: consent, audit, deletion, no PII in metadata
  4. No diagnostic language anywhere in the API surface (spot check)
"""

import pytest

from tests.conftest import TEST_USER_ID

# ─── Security headers ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_security_headers_present_on_scan_endpoint(client, auth_headers):
    """All required security headers must be present on API responses."""
    resp = await client.get("/api/v1/scans/history", headers=auth_headers)
    assert resp.status_code == 200

    headers = resp.headers
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    assert headers.get("referrer-policy") == "no-referrer"
    assert headers.get("cache-control") == "no-store"
    assert headers.get("permissions-policy") is not None


@pytest.mark.asyncio
async def test_security_headers_present_on_health_endpoint(client):
    """Security headers should appear even on the health endpoint."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.asyncio
async def test_process_time_header_present(client, auth_headers):
    """X-Process-Time-Ms must be present (timing middleware)."""
    resp = await client.get("/api/v1/scans/history", headers=auth_headers)
    assert "x-process-time-ms" in resp.headers


# ─── Rate limiting ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_rate_limit_blocks_excessive_sessions(client, auth_headers, monkeypatch):
    """Creating more sessions than the hourly limit returns 429."""
    from app.config import settings

    monkeypatch.setattr(settings, "scan_rate_limit_per_hour", 2)

    # Need active consent first — grant it for the authenticated user (TEST_USER_ID)
    await client.post(
        "/api/v1/consent",
        json={"user_id": TEST_USER_ID, "consent_version": "1.0", "purpose": "wellness_screening"},
        headers=auth_headers,
    )

    # Create sessions up to the limit
    for _ in range(2):
        resp = await client.post(
            "/api/v1/scans/sessions",
            json={"user_id": TEST_USER_ID},
            headers=auth_headers,
        )
        assert resp.status_code == 201

    # Next one should be rate-limited
    resp = await client.post(
        "/api/v1/scans/sessions",
        json={"user_id": TEST_USER_ID},
        headers=auth_headers,
    )
    assert resp.status_code == 429
    assert "rate limit" in resp.json()["detail"].lower()


# ─── DPDP compliance checklist ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dpdp_consent_grant_revoke_cycle(client, auth_headers):
    """Consent can be granted and revoked; status reflects current state."""
    user_id = TEST_USER_ID

    await client.post(
        "/api/v1/consent",
        json={"user_id": user_id, "consent_version": "1.0", "purpose": "wellness_screening"},
        headers=auth_headers,
    )
    status_resp = await client.get(
        "/api/v1/consent/status",
        params={"user_id": user_id},
        headers=auth_headers,
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["has_active_consent"] is True

    await client.post(
        "/api/v1/consent/revoke",
        json={"user_id": user_id},
        headers=auth_headers,
    )
    status_resp = await client.get(
        "/api/v1/consent/status",
        params={"user_id": user_id},
        headers=auth_headers,
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["has_active_consent"] is False


@pytest.mark.asyncio
async def test_dpdp_deletion_request_accepted(client, auth_headers):
    """Data deletion request must be accepted and reflected in consent status."""
    user_id = TEST_USER_ID

    await client.post(
        "/api/v1/consent",
        json={"user_id": user_id, "consent_version": "1.0", "purpose": "wellness_screening"},
        headers=auth_headers,
    )
    del_resp = await client.post(
        "/api/v1/consent/deletion-request",
        json={"user_id": user_id},
        headers=auth_headers,
    )
    assert del_resp.status_code in (200, 201)
    status_resp = await client.get(
        "/api/v1/consent/status",
        params={"user_id": user_id},
        headers=auth_headers,
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["deletion_requested"] is True


@pytest.mark.asyncio
async def test_dpdp_scan_result_contains_no_pii_fields(client, auth_headers):
    """Scan results must not expose name, email, phone, or date_of_birth fields."""
    forbidden_pii_fields = {"name", "email", "phone", "date_of_birth", "address", "aadhaar"}
    user_id = TEST_USER_ID

    await client.post(
        "/api/v1/consent",
        json={"user_id": user_id, "consent_version": "1.0", "purpose": "wellness_screening"},
        headers=auth_headers,
    )
    session_resp = await client.post(
        "/api/v1/scans/sessions",
        json={"user_id": user_id},
        headers=auth_headers,
    )
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]

    result_resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json={
            "hr_bpm": 70.0,
            "quality_score": 0.80,
            "lighting_score": 0.72,
            "motion_score": 0.96,
            "face_confidence": 0.83,
            "audio_snr_db": 20.0,
            "flags": [],
        },
        headers=auth_headers,
    )
    assert result_resp.status_code == 200
    result_keys = set(result_resp.json().keys())
    assert result_keys.isdisjoint(
        forbidden_pii_fields
    ), f"PII fields found in scan result: {result_keys & forbidden_pii_fields}"


@pytest.mark.asyncio
async def test_audit_log_accessible_to_authenticated_user(client, auth_headers):
    """Audit log endpoint must be accessible and return log entries."""
    resp = await client.get("/api/v1/audit/logs", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data or isinstance(data, list)


# ─── No diagnostic language ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_root_response_contains_no_diagnostic_language(client):
    """Root API response must not contain diagnostic language."""
    resp = await client.get("/")
    text = resp.text.lower()
    for word in ["disease", "disorder", "treat", "cure"]:
        assert word not in text, f"Diagnostic language found in root response: '{word}'"


@pytest.mark.asyncio
async def test_openapi_description_contains_disclaimer(client):
    """OpenAPI spec must include the wellness disclaimer."""
    openapi_resp = await client.get("/openapi.json")
    assert openapi_resp.status_code == 200
    assert "wellness" in openapi_resp.text.lower()
