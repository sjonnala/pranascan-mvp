"""Tests for closed beta onboarding endpoints."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.beta import BetaEnrollment, BetaInvite
from tests.conftest import TEST_USER_ID


async def _create_invite(
    db: AsyncSession,
    *,
    code: str = "BETA50",
    cohort_name: str = "proactive_professionals",
    max_redemptions: int = 50,
    redemption_count: int = 0,
    is_active: bool = True,
    expires_at: datetime | None = None,
) -> BetaInvite:
    invite = BetaInvite(
        code=code,
        cohort_name=cohort_name,
        max_redemptions=max_redemptions,
        redemption_count=redemption_count,
        is_active=is_active,
        expires_at=expires_at,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite


@pytest.mark.asyncio
async def test_beta_status_returns_disabled_when_feature_off(
    client: AsyncClient, auth_headers: dict
):
    with patch("app.routers.beta.settings.beta_onboarding_enabled", False):
        resp = await client.get("/api/v1/beta/status", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == TEST_USER_ID
    assert data["beta_onboarding_enabled"] is False
    assert data["enrolled"] is False
    assert data["invite_required"] is False


@pytest.mark.asyncio
async def test_redeem_beta_invite_enrolls_user(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    await _create_invite(db_session, code="CLOSED50", cohort_name="remote_caregivers")

    with patch("app.routers.beta.settings.beta_onboarding_enabled", True):
        resp = await client.post(
            "/api/v1/beta/redeem",
            json={"invite_code": "closed50"},
            headers=auth_headers,
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["enrolled"] is True
        assert data["invite_required"] is False
        assert data["cohort_name"] == "remote_caregivers"
        assert data["invite_code"] == "CLOSED50"

        status_resp = await client.get("/api/v1/beta/status", headers=auth_headers)

    assert status_resp.status_code == 200
    assert status_resp.json()["enrolled"] is True

    invite_row = await db_session.execute(select(BetaInvite).where(BetaInvite.code == "CLOSED50"))
    invite = invite_row.scalar_one()
    assert invite.redemption_count == 1

    enrollment_row = await db_session.execute(
        select(BetaEnrollment).where(BetaEnrollment.user_id == TEST_USER_ID)
    )
    enrollment = enrollment_row.scalar_one()
    assert enrollment.cohort_name == "remote_caregivers"


@pytest.mark.asyncio
async def test_redeem_beta_invite_requires_valid_code(
    client: AsyncClient, auth_headers: dict
):
    with patch("app.routers.beta.settings.beta_onboarding_enabled", True):
        resp = await client.post(
            "/api/v1/beta/redeem",
            json={"invite_code": "missing"},
            headers=auth_headers,
        )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Invite code not found."


@pytest.mark.asyncio
async def test_redeem_beta_invite_rejects_expired_code(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    await _create_invite(
        db_session,
        code="EXPIRED",
        expires_at=datetime.now(tz=timezone.utc) - timedelta(days=1),
    )

    with patch("app.routers.beta.settings.beta_onboarding_enabled", True):
        resp = await client.post(
            "/api/v1/beta/redeem",
            json={"invite_code": "EXPIRED"},
            headers=auth_headers,
        )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Invite code has expired."


@pytest.mark.asyncio
async def test_redeem_beta_invite_rejects_fully_redeemed_code(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    await _create_invite(
        db_session,
        code="FULL",
        max_redemptions=1,
        redemption_count=1,
    )

    with patch("app.routers.beta.settings.beta_onboarding_enabled", True):
        resp = await client.post(
            "/api/v1/beta/redeem",
            json={"invite_code": "FULL"},
            headers=auth_headers,
        )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Invite code has already reached its redemption limit."


@pytest.mark.asyncio
async def test_redeem_beta_invite_is_idempotent_for_existing_enrollment(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    invite = await _create_invite(db_session, code="FOUNDERS", cohort_name="founding_users")
    db_session.add(
        BetaEnrollment(
            user_id=TEST_USER_ID,
            invite_id=invite.id,
            invite_code=invite.code,
            cohort_name=invite.cohort_name,
        )
    )
    invite.redemption_count = 1
    await db_session.commit()

    with patch("app.routers.beta.settings.beta_onboarding_enabled", True):
        resp = await client.post(
            "/api/v1/beta/redeem",
            json={"invite_code": "OTHERCODE"},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["enrolled"] is True
    assert data["invite_code"] == "FOUNDERS"
    assert data["cohort_name"] == "founding_users"
