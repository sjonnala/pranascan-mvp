"""Auth router — token issuance and refresh."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import settings
from app.middleware.auth import require_auth
from app.schemas.auth import RefreshRequest, TokenRequest, TokenResponse, UserInfo
from app.services.auth_service import create_access_token, create_refresh_token, decode_token

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/token", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def issue_token(body: TokenRequest) -> TokenResponse:
    """
    Issue a JWT access + refresh token pair for a user.

    Development mode: user_id only (no password required).
    Production: integrate with OTP / password verification before release.
    """
    access = create_access_token(body.user_id)
    refresh = create_refresh_token(body.user_id)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def refresh_token(body: RefreshRequest) -> TokenResponse:
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
    )


@router.get("/me", response_model=UserInfo)
async def get_me(user_id: str = Depends(require_auth)) -> UserInfo:
    """Return the authenticated user's info decoded from their token."""
    return UserInfo(user_id=user_id, token_type="access")
