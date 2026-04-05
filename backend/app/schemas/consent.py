"""Pydantic v2 schemas for consent endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class ConsentGrantRequest(BaseModel):
    user_id: str = Field(..., description="Pseudonymous user UUID; must match the authenticated subject.")
    consent_version: str = Field(default="1.0")
    purpose: str = Field(
        default="wellness_screening",
        description="Purpose for which consent is granted",
    )
    ip_address: str | None = None
    user_agent: str | None = None


class ConsentRevokeRequest(BaseModel):
    user_id: str = Field(..., description="Pseudonymous user UUID; must match the authenticated subject.")
    reason: str | None = Field(default=None, max_length=256)


class ConsentDeletionRequest(BaseModel):
    user_id: str = Field(..., description="Pseudonymous user UUID; must match the authenticated subject.")
    reason: str | None = Field(default=None, max_length=256)


class ConsentStatusResponse(BaseModel):
    user_id: str
    has_active_consent: bool
    consent_version: str | None
    granted_at: datetime | None
    revoked_at: datetime | None
    deletion_requested: bool
    deletion_scheduled_at: datetime | None

    model_config = {"from_attributes": True}


class ConsentRecordResponse(BaseModel):
    id: str
    user_id: str
    action: str
    consent_version: str
    purpose: str
    created_at: datetime
    deletion_scheduled_at: datetime | None = None

    model_config = {"from_attributes": True}
