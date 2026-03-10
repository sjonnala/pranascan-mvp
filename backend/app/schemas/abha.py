"""Pydantic v2 schemas for ABHA integration endpoints."""

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# ABHA ID: 14 digits, optionally formatted as XX-XXXX-XXXX-XXXX
_ABHA_RAW_RE = re.compile(r"^\d{14}$")
_ABHA_FMT_RE = re.compile(r"^\d{2}-\d{4}-\d{4}-\d{4}$")


def _normalise_abha(v: str) -> str:
    """Strip hyphens, validate digit count, return canonical formatted form."""
    stripped = v.replace("-", "").strip()
    if not stripped.isdigit() or len(stripped) != 14:
        raise ValueError(
            "abha_id must be a 14-digit number (e.g. 91-2345-6789-0123)"
        )
    return f"{stripped[:2]}-{stripped[2:6]}-{stripped[6:10]}-{stripped[10:14]}"


class AbhaLinkRequest(BaseModel):
    """Body for POST /abha/link."""

    abha_id: str = Field(
        ...,
        description="14-digit ABHA ID, with or without hyphens (e.g. 91-2345-6789-0123)",
        examples=["91-2345-6789-0123"],
    )

    @field_validator("abha_id", mode="before")
    @classmethod
    def validate_abha_id(cls, v: str) -> str:
        return _normalise_abha(v)


class AbhaLinkResponse(BaseModel):
    """Response from POST /abha/link."""

    user_id: str
    abha_id: str
    linked_at: datetime
    sandbox: bool = Field(description="True when using sandbox/mock ABDM gateway")

    model_config = {"from_attributes": True}


class AbhaStatusResponse(BaseModel):
    """Response from GET /abha/status."""

    user_id: str
    linked: bool
    abha_id: str | None = None
    linked_at: datetime | None = None
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None
    abha_enabled: bool = Field(description="Whether ABHA integration is enabled on this server")
    sandbox: bool = Field(description="True when using sandbox/mock ABDM gateway")

    model_config = {"from_attributes": True}


class AbhaSyncRequest(BaseModel):
    """Body for POST /abha/sync/{session_id} (manual sync trigger)."""

    # No body fields required — session_id and user come from path + auth
    pass


class AbhaSyncResponse(BaseModel):
    """Response from POST /abha/sync/{session_id}."""

    session_id: str
    abha_id: str | None
    status: str  # "success" | "skipped_disabled" | "skipped_no_link" | "failed"
    gateway_ref: str | None = None
    sandbox: bool
    synced_at: datetime

    model_config = {"from_attributes": True}
