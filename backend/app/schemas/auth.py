"""Auth schemas — OTP verification and token responses."""

import re

from pydantic import BaseModel, Field, field_validator


class OTPRequestSchema(BaseModel):
    """Request body for POST /auth/otp/request."""

    phone: str = Field(..., description="Phone number in E.164 format (e.g. +91XXXXXXXXXX)")

    @field_validator("phone")
    @classmethod
    def normalize_phone_e164(cls, v: str) -> str:
        # Strip whitespace and dashes
        cleaned = re.sub(r"[\s\-()]", "", v.strip())
        if not re.match(r"^\+[1-9]\d{6,14}$", cleaned):
            raise ValueError("Phone must be in E.164 format (e.g. +91XXXXXXXXXX)")
        return cleaned


class OTPVerifySchema(BaseModel):
    """Request body for POST /auth/otp/verify."""

    phone: str = Field(..., description="Phone number in E.164 format")
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")

    @field_validator("phone")
    @classmethod
    def normalize_phone_e164(cls, v: str) -> str:
        cleaned = re.sub(r"[\s\-()]", "", v.strip())
        if not re.match(r"^\+[1-9]\d{6,14}$", cleaned):
            raise ValueError("Phone must be in E.164 format (e.g. +91XXXXXXXXXX)")
        return cleaned

    @field_validator("otp")
    @classmethod
    def otp_must_be_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("OTP must contain only digits")
        return v


class TokenResponse(BaseModel):
    """JWT access + refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access token lifetime in seconds")
    user_id: str = Field(..., description="User UUID")


class RefreshRequest(BaseModel):
    refresh_token: str


class UserInfo(BaseModel):
    """Decoded token payload returned by /auth/me."""

    user_id: str
    token_type: str  # "access" or "refresh"
