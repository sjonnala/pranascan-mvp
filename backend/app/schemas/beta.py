"""Schemas for closed-beta onboarding."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class BetaInviteRedeemRequest(BaseModel):
    invite_code: str = Field(..., min_length=3, max_length=64)

    @field_validator("invite_code")
    @classmethod
    def normalize_invite_code(cls, value: str) -> str:
        code = value.strip().upper()
        if not code:
            raise ValueError("Invite code cannot be blank.")
        return code


class BetaStatusResponse(BaseModel):
    user_id: str
    beta_onboarding_enabled: bool
    enrolled: bool
    invite_required: bool
    cohort_name: str | None = None
    invite_code: str | None = None
    enrolled_at: datetime | None = None
