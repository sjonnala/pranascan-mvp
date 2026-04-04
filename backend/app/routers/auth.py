"""Auth router — OTP-based phone verification and token management."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import require_auth
from app.schemas.auth import (
    OTPRequestSchema,
    OTPVerifySchema,
    RefreshRequest,
    TokenResponse,
    UserInfo,
)
from app.services.auth_service import create_access_token, create_refresh_token, decode_token
from app.services.otp_service import create_otp, get_or_create_user, verify_otp

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/otp/request", status_code=status.HTTP_200_OK)
async def request_otp(
    body: OTPRequestSchema,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Request a one-time password for phone verification.

    Generates a 6-digit OTP, stores a hashed copy with a 10-minute TTL,
    and delivers it via the configured delivery channel (stdout stub for dev).
    """
    otp = await create_otp(db, body.phone)
    # In dev mode, return the OTP in the response for testing convenience.
    # In production, the OTP is delivered via SMS only.
    response: dict = {"message": "OTP sent successfully."}
    if settings.environment != "production":
        response["otp"] = otp
    return response


@router.post("/otp/verify", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def verify_otp_endpoint(
    body: OTPVerifySchema,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Verify an OTP and issue tokens.

    On success: upserts the User row (creates on first login),
    marks OTP as consumed, returns access + refresh tokens.
    """
    success, message = await verify_otp(db, body.phone, body.otp)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    user = await get_or_create_user(db, body.phone)
    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
        user_id=user.id,
    )


@router.post("/token", status_code=status.HTTP_410_GONE)
async def issue_token_gone() -> dict:
    """
    REMOVED — the old dev-mode token stub.

    This endpoint accepted any UUID and issued tokens without verification.
    Use POST /auth/otp/request and POST /auth/otp/verify instead.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "This endpoint has been removed. "
            "Use POST /auth/otp/request to get an OTP, "
            "then POST /auth/otp/verify to authenticate."
        ),
    )


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def refresh_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange a valid refresh token for a new access + refresh pair."""
    payload = decode_token(body.refresh_token)

    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = payload["sub"]
    access = create_access_token(user_id)
    new_refresh = create_refresh_token(user_id)
    return TokenResponse(
        access_token=access,
        refresh_token=new_refresh,
        expires_in=settings.access_token_expire_minutes * 60,
        user_id=user_id,
    )


@router.get("/me", response_model=UserInfo)
async def get_me(user_id: str = Depends(require_auth)) -> UserInfo:
    """Return the authenticated user's info decoded from their token."""
    return UserInfo(user_id=user_id, token_type="access")
