"""Schemas for post-scan feedback endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

UsefulResponse = Literal["useful", "needs_work"]


class FeedbackCreateRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=36)
    useful_response: UsefulResponse
    nps_score: int | None = Field(default=None, ge=0, le=10)
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class FeedbackResponse(BaseModel):
    id: str
    session_id: str
    user_id: str
    useful_response: UsefulResponse
    nps_score: int | None
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
