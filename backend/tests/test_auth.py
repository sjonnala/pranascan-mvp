"""Tests for JWT auth enforcement and token service."""

import pytest
from httpx import AsyncClient

from app.config import settings
from app.services.auth_service import create_access_token, create_refresh_token, decode_token
from tests.conftest import TEST_USER_ID

# ---------------------------------------------------------------------------
# /auth/me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_me_with_valid_token(client: AsyncClient):
    """GET /auth/me returns user info for valid token."""
    token = create_access_token(TEST_USER_ID)
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == TEST_USER_ID
    assert data["token_type"] == "access"


@pytest.mark.asyncio
async def test_get_me_no_token(client: AsyncClient):
    """GET /auth/me without token returns 403."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_me_tampered_token(client: AsyncClient):
    """Tampered token is rejected with 401."""
    token = create_access_token(TEST_USER_ID)
    tampered = token[:-5] + "XXXXX"
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tampered}"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Expired token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_token_rejected(client: AsyncClient):
    """An expired token (exp in the past) is rejected."""
    from datetime import datetime, timedelta, timezone

    from jose import jwt as jose_jwt

    past_exp = datetime.now(tz=timezone.utc) - timedelta(seconds=1)
    payload = {
        "sub": TEST_USER_ID,
        "type": "access",
        "exp": past_exp,
        "iat": datetime.now(tz=timezone.utc) - timedelta(seconds=10),
    }
    expired_token = jose_jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)

    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Refresh token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_token_issues_new_pair(client: AsyncClient):
    """POST /auth/refresh with valid refresh token returns new token pair."""
    refresh = create_refresh_token(TEST_USER_ID)
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_refresh_with_access_token_rejected(client: AsyncClient):
    """Passing an access token to /auth/refresh is rejected."""
    access = create_access_token(TEST_USER_ID)
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": access})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Old stub endpoint returns 410
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_old_token_stub_returns_410(client: AsyncClient):
    """POST /auth/token (old dev stub) now returns 410 Gone."""
    resp = await client.post("/api/v1/auth/token", json={"user_id": TEST_USER_ID})
    assert resp.status_code == 410


# ---------------------------------------------------------------------------
# Service-level unit tests
# ---------------------------------------------------------------------------


def test_decode_token_returns_none_for_garbage():
    """decode_token returns None for non-JWT strings."""
    assert decode_token("not-a-jwt") is None


def test_decode_token_returns_none_for_tampered():
    """decode_token returns None for a tampered JWT."""
    token = create_access_token(TEST_USER_ID)
    tampered = token[:-4] + "ZZZZ"
    assert decode_token(tampered) is None


def test_access_token_has_correct_type():
    token = create_access_token(TEST_USER_ID)
    payload = decode_token(token)
    assert payload is not None
    assert payload["type"] == "access"
    assert payload["sub"] == TEST_USER_ID


def test_refresh_token_has_correct_type():
    token = create_refresh_token(TEST_USER_ID)
    payload = decode_token(token)
    assert payload is not None
    assert payload["type"] == "refresh"
