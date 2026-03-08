"""Tests for consent & privacy flow endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import TEST_USER_ID


@pytest.mark.asyncio
async def test_grant_consent(client: AsyncClient):
    """POST /consent returns 201 with consent record."""
    resp = await client.post(
        "/api/v1/consent",
        json={"user_id": TEST_USER_ID, "consent_version": "1.0", "purpose": "wellness_screening"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["user_id"] == TEST_USER_ID
    assert data["action"] == "granted"
    assert data["consent_version"] == "1.0"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_consent_status_no_consent(client: AsyncClient):
    """GET /consent/status returns inactive for unknown user."""
    resp = await client.get("/api/v1/consent/status", params={"user_id": TEST_USER_ID})
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_active_consent"] is False
    assert data["granted_at"] is None


@pytest.mark.asyncio
async def test_consent_status_after_grant(client: AsyncClient):
    """After granting consent, status shows active."""
    await client.post(
        "/api/v1/consent",
        json={"user_id": TEST_USER_ID, "consent_version": "1.0", "purpose": "wellness_screening"},
    )
    resp = await client.get("/api/v1/consent/status", params={"user_id": TEST_USER_ID})
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_active_consent"] is True
    assert data["granted_at"] is not None
    assert data["revoked_at"] is None


@pytest.mark.asyncio
async def test_revoke_consent(client: AsyncClient):
    """After revoking, status shows inactive."""
    await client.post(
        "/api/v1/consent",
        json={"user_id": TEST_USER_ID, "consent_version": "1.0", "purpose": "wellness_screening"},
    )
    resp = await client.post("/api/v1/consent/revoke", json={"user_id": TEST_USER_ID})
    assert resp.status_code == 201
    assert resp.json()["action"] == "revoked"

    status_resp = await client.get("/api/v1/consent/status", params={"user_id": TEST_USER_ID})
    assert status_resp.json()["has_active_consent"] is False
    assert status_resp.json()["revoked_at"] is not None


@pytest.mark.asyncio
async def test_deletion_request(client: AsyncClient):
    """Deletion request sets deletion_scheduled_at 30 days out."""
    await client.post(
        "/api/v1/consent",
        json={"user_id": TEST_USER_ID, "consent_version": "1.0", "purpose": "wellness_screening"},
    )
    resp = await client.post("/api/v1/consent/deletion-request", json={"user_id": TEST_USER_ID})
    assert resp.status_code == 201
    assert resp.json()["action"] == "deletion_requested"
    assert resp.json()["deletion_scheduled_at"] is not None

    status_resp = await client.get("/api/v1/consent/status", params={"user_id": TEST_USER_ID})
    assert status_resp.json()["deletion_requested"] is True
    assert status_resp.json()["has_active_consent"] is False


@pytest.mark.asyncio
async def test_regrant_after_revoke(client: AsyncClient):
    """Re-granting consent after revocation restores active status."""
    await client.post(
        "/api/v1/consent",
        json={"user_id": TEST_USER_ID, "consent_version": "1.0", "purpose": "wellness_screening"},
    )
    await client.post("/api/v1/consent/revoke", json={"user_id": TEST_USER_ID})
    await client.post(
        "/api/v1/consent",
        json={"user_id": TEST_USER_ID, "consent_version": "1.0", "purpose": "wellness_screening"},
    )
    status_resp = await client.get("/api/v1/consent/status", params={"user_id": TEST_USER_ID})
    assert status_resp.json()["has_active_consent"] is True
