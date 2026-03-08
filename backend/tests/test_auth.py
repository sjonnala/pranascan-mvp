"""Tests for JWT auth endpoints and enforcement."""


import pytest
from httpx import AsyncClient
from jose import jwt

from app.config import settings
from app.services.auth_service import create_access_token, create_refresh_token, decode_token
from tests.conftest import TEST_USER_ID

# ---------------------------------------------------------------------------
# Token issuance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issue_token(client: AsyncClient):
    """POST /auth/token returns access + refresh tokens."""
    resp = await client.post("/api/v1/auth/token", json={"user_id": TEST_USER_ID})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_issued_token_is_valid_jwt(client: AsyncClient):
    """Issued access token is a valid JWT with correct sub."""
    resp = await client.post("/api/v1/auth/token", json={"user_id": TEST_USER_ID})
    token = resp.json()["access_token"]
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    assert payload["sub"] == TEST_USER_ID
    assert payload["type"] == "access"


# ---------------------------------------------------------------------------
# /auth/me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_me_with_valid_token(client: AsyncClient):
    """GET /auth/me returns user info for valid token."""
    token_resp = await client.post("/api/v1/auth/token", json={"user_id": TEST_USER_ID})
    token = token_resp.json()["access_token"]

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
    token_resp = await client.post("/api/v1/auth/token", json={"user_id": TEST_USER_ID})
    token = token_resp.json()["access_token"]
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
    token_resp = await client.post("/api/v1/auth/token", json={"user_id": TEST_USER_ID})
    refresh = token_resp.json()["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_refresh_with_access_token_rejected(client: AsyncClient):
    """Passing an access token to /auth/refresh is rejected."""
    token_resp = await client.post("/api/v1/auth/token", json={"user_id": TEST_USER_ID})
    access = token_resp.json()["access_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": access})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# service-level unit tests
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
