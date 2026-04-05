"""Tests for OTP-based phone authentication."""

import pytest
from httpx import AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.otp import OTPRequest

TEST_PHONE = "+919876543210"


# ---------------------------------------------------------------------------
# POST /auth/otp/request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_otp_success(client: AsyncClient):
    """POST /auth/otp/request returns 200 and OTP in dev mode."""
    resp = await client.post("/api/v1/auth/otp/request", json={"phone": TEST_PHONE})
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "OTP sent successfully."
    # In dev mode, OTP is returned for testing convenience
    assert "otp" in data
    assert len(data["otp"]) == 6
    assert data["otp"].isdigit()


@pytest.mark.asyncio
async def test_request_otp_invalid_phone(client: AsyncClient):
    """POST /auth/otp/request with invalid phone returns 422."""
    resp = await client.post("/api/v1/auth/otp/request", json={"phone": "not-a-phone"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_request_otp_normalizes_phone(client: AsyncClient):
    """Phone numbers with spaces/dashes are normalized."""
    resp = await client.post("/api/v1/auth/otp/request", json={"phone": "+91 987-654-3210"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /auth/otp/verify — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_otp_success(client: AsyncClient):
    """Full flow: request OTP → verify → get tokens."""
    # Request OTP
    req_resp = await client.post("/api/v1/auth/otp/request", json={"phone": TEST_PHONE})
    otp = req_resp.json()["otp"]

    # Verify OTP
    verify_resp = await client.post(
        "/api/v1/auth/otp/verify", json={"phone": TEST_PHONE, "otp": otp}
    )
    assert verify_resp.status_code == 200
    data = verify_resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0
    assert "user_id" in data

    # Verify the access token is a valid JWT with correct sub
    payload = jwt.decode(data["access_token"], settings.secret_key, algorithms=[settings.algorithm])
    assert payload["sub"] == data["user_id"]
    assert payload["type"] == "access"


@pytest.mark.asyncio
async def test_verify_otp_creates_user(client: AsyncClient):
    """First OTP verification creates a new user."""
    req_resp = await client.post("/api/v1/auth/otp/request", json={"phone": TEST_PHONE})
    otp = req_resp.json()["otp"]

    verify_resp = await client.post(
        "/api/v1/auth/otp/verify", json={"phone": TEST_PHONE, "otp": otp}
    )
    user_id = verify_resp.json()["user_id"]
    assert user_id  # non-empty UUID


@pytest.mark.asyncio
async def test_verify_otp_relogin_returns_same_user(client: AsyncClient):
    """Re-login with same phone returns the same user_id (upsert, not duplicate)."""
    # First login
    req1 = await client.post("/api/v1/auth/otp/request", json={"phone": TEST_PHONE})
    otp1 = req1.json()["otp"]
    verify1 = await client.post(
        "/api/v1/auth/otp/verify", json={"phone": TEST_PHONE, "otp": otp1}
    )
    user_id_1 = verify1.json()["user_id"]

    # Second login
    req2 = await client.post("/api/v1/auth/otp/request", json={"phone": TEST_PHONE})
    otp2 = req2.json()["otp"]
    verify2 = await client.post(
        "/api/v1/auth/otp/verify", json={"phone": TEST_PHONE, "otp": otp2}
    )
    user_id_2 = verify2.json()["user_id"]

    assert user_id_1 == user_id_2


# ---------------------------------------------------------------------------
# POST /auth/otp/verify — failure cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_otp_wrong_code(client: AsyncClient):
    """Wrong OTP returns 400."""
    await client.post("/api/v1/auth/otp/request", json={"phone": TEST_PHONE})

    resp = await client.post(
        "/api/v1/auth/otp/verify", json={"phone": TEST_PHONE, "otp": "000000"}
    )
    assert resp.status_code == 400
    assert "Invalid OTP" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_verify_otp_expired(client: AsyncClient, db_session: AsyncSession):
    """Expired OTP returns 400."""
    from datetime import datetime, timedelta, timezone

    # Request OTP normally
    req_resp = await client.post("/api/v1/auth/otp/request", json={"phone": TEST_PHONE})
    otp = req_resp.json()["otp"]

    # Manually expire the OTP in the database
    from sqlalchemy import update

    stmt = (
        update(OTPRequest)
        .where(OTPRequest.phone_e164 == TEST_PHONE)
        .values(expires_at=datetime.now(tz=timezone.utc) - timedelta(minutes=1))
    )
    await db_session.execute(stmt)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/auth/otp/verify", json={"phone": TEST_PHONE, "otp": otp}
    )
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_verify_otp_rate_limit(client: AsyncClient, db_session: AsyncSession):
    """After 5 failed attempts, further attempts are rejected."""
    from sqlalchemy import update

    req_resp = await client.post("/api/v1/auth/otp/request", json={"phone": TEST_PHONE})
    otp = req_resp.json()["otp"]

    # Directly set failed_attempts to MAX (5) on the OTP record to simulate
    # 5 prior failures. This avoids relying on per-request commit semantics
    # in the test harness.
    stmt = (
        update(OTPRequest)
        .where(OTPRequest.phone_e164 == TEST_PHONE, OTPRequest.consumed_at.is_(None))
        .values(failed_attempts=5)
    )
    await db_session.execute(stmt)
    await db_session.commit()

    # Next attempt — should be rate-limited even with correct OTP
    resp = await client.post(
        "/api/v1/auth/otp/verify", json={"phone": TEST_PHONE, "otp": otp}
    )
    assert resp.status_code == 400
    assert "Too many failed attempts" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_verify_otp_no_pending(client: AsyncClient):
    """Verify without requesting first returns 400."""
    resp = await client.post(
        "/api/v1/auth/otp/verify", json={"phone": TEST_PHONE, "otp": "123456"}
    )
    assert resp.status_code == 400
    assert "No pending OTP" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_verify_otp_already_consumed(client: AsyncClient):
    """OTP cannot be reused after successful verification."""
    req_resp = await client.post("/api/v1/auth/otp/request", json={"phone": TEST_PHONE})
    otp = req_resp.json()["otp"]

    # First verify — success
    resp1 = await client.post(
        "/api/v1/auth/otp/verify", json={"phone": TEST_PHONE, "otp": otp}
    )
    assert resp1.status_code == 200

    # Second verify — should fail (consumed)
    resp2 = await client.post(
        "/api/v1/auth/otp/verify", json={"phone": TEST_PHONE, "otp": otp}
    )
    assert resp2.status_code == 400


# ---------------------------------------------------------------------------
# POST /auth/token — 410 Gone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_old_token_endpoint_returns_410(client: AsyncClient):
    """The old dev stub POST /auth/token now returns 410 Gone."""
    resp = await client.post("/api/v1/auth/token", json={"user_id": "any-uuid"})
    assert resp.status_code == 410
    assert "removed" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /auth/refresh — still works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_after_otp_login(client: AsyncClient):
    """Refresh token from OTP login can be used to get new tokens."""
    # Login via OTP
    req_resp = await client.post("/api/v1/auth/otp/request", json={"phone": TEST_PHONE})
    otp = req_resp.json()["otp"]
    verify_resp = await client.post(
        "/api/v1/auth/otp/verify", json={"phone": TEST_PHONE, "otp": otp}
    )
    refresh = verify_resp.json()["refresh_token"]

    # Refresh
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


# ---------------------------------------------------------------------------
# GET /auth/me — still works with OTP-issued tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_with_otp_token(client: AsyncClient):
    """GET /auth/me works with tokens issued by OTP flow."""
    req_resp = await client.post("/api/v1/auth/otp/request", json={"phone": TEST_PHONE})
    otp = req_resp.json()["otp"]
    verify_resp = await client.post(
        "/api/v1/auth/otp/verify", json={"phone": TEST_PHONE, "otp": otp}
    )
    token = verify_resp.json()["access_token"]
    user_id = verify_resp.json()["user_id"]

    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["user_id"] == user_id


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_otp_must_be_6_digits(client: AsyncClient):
    """OTP must be exactly 6 digits."""
    await client.post("/api/v1/auth/otp/request", json={"phone": TEST_PHONE})

    # Too short
    resp = await client.post(
        "/api/v1/auth/otp/verify", json={"phone": TEST_PHONE, "otp": "123"}
    )
    assert resp.status_code == 422

    # Non-digits
    resp = await client.post(
        "/api/v1/auth/otp/verify", json={"phone": TEST_PHONE, "otp": "abcdef"}
    )
    assert resp.status_code == 422
