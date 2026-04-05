"""Closed-beta onboarding router."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import require_auth
from app.models.beta import BetaEnrollment, BetaInvite
from app.schemas.beta import BetaInviteRedeemRequest, BetaStatusResponse

router = APIRouter(prefix="/beta", tags=["Beta Onboarding"])


async def _get_enrollment(db: AsyncSession, user_id: str) -> BetaEnrollment | None:
    result = await db.execute(select(BetaEnrollment).where(BetaEnrollment.user_id == user_id))
    return result.scalar_one_or_none()


def _status_payload(user_id: str, enrollment: BetaEnrollment | None) -> BetaStatusResponse:
    return BetaStatusResponse(
        user_id=user_id,
        beta_onboarding_enabled=settings.beta_onboarding_enabled,
        enrolled=enrollment is not None,
        invite_required=settings.beta_onboarding_enabled and enrollment is None,
        cohort_name=enrollment.cohort_name if enrollment else None,
        invite_code=enrollment.invite_code if enrollment else None,
        enrolled_at=enrollment.enrolled_at if enrollment else None,
    )


@router.get("/status", response_model=BetaStatusResponse)
async def get_beta_status(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_auth),
) -> BetaStatusResponse:
    """Return current closed-beta enrollment status for the authenticated user."""
    enrollment = await _get_enrollment(db, user_id)
    return _status_payload(user_id, enrollment)


@router.post("/redeem", response_model=BetaStatusResponse, status_code=status.HTTP_200_OK)
async def redeem_beta_invite(
    body: BetaInviteRedeemRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_auth),
) -> BetaStatusResponse:
    """
    Redeem a closed-beta invite code for the authenticated user.

    The endpoint is idempotent for already-enrolled users and does not require
    the client to know whether enrollment already exists.
    """
    if not settings.beta_onboarding_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Closed beta onboarding is not enabled on this deployment.",
        )

    enrollment = await _get_enrollment(db, user_id)
    if enrollment is not None:
        return _status_payload(user_id, enrollment)

    result = await db.execute(select(BetaInvite).where(BetaInvite.code == body.invite_code))
    invite = result.scalar_one_or_none()
    if invite is None or invite.is_active is not True:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite code not found.",
        )

    now = datetime.now(tz=timezone.utc)
    expires_at = invite.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at is not None and expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invite code has expired.",
        )

    if invite.redemption_count >= invite.max_redemptions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invite code has already reached its redemption limit.",
        )

    enrollment = BetaEnrollment(
        user_id=user_id,
        invite_id=invite.id,
        invite_code=invite.code,
        cohort_name=invite.cohort_name,
    )
    invite.redemption_count += 1
    db.add(enrollment)
    await db.flush()
    await db.refresh(enrollment)

    return _status_payload(user_id, enrollment)
