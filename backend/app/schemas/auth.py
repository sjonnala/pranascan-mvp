"""Auth schemas — token issue and user info."""

from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    """Request body for token issuance (dev: user_id only; prod: add password/OTP)."""

    user_id: str = Field(..., description="User identifier (UUID)")


class TokenResponse(BaseModel):
    """JWT access + refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access token lifetime in seconds")


class RefreshRequest(BaseModel):
    refresh_token: str


class UserInfo(BaseModel):
    """Decoded token payload returned by /auth/me."""

    user_id: str
    token_type: str  # "access" or "refresh"
