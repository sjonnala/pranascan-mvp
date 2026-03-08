"""Pydantic v2 schemas for scan session endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ScanSessionCreateRequest(BaseModel):
    user_id: str = Field(..., description="Pseudonymous user UUID")
    device_model: str | None = Field(default=None, max_length=128)
    app_version: str | None = Field(default=None, max_length=32)


class ScanResultSubmit(BaseModel):
    """
    Wellness indicator values computed on-device.
    Raw video/audio is never sent — edge processing only.
    These are wellness indicators, not diagnostic values.
    """

    # Wellness indicators
    hr_bpm: float | None = Field(default=None, ge=30.0, le=220.0)
    hrv_ms: float | None = Field(default=None, ge=0.0, le=500.0)
    respiratory_rate: float | None = Field(default=None, ge=4.0, le=60.0)
    voice_jitter_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    voice_shimmer_pct: float | None = Field(default=None, ge=0.0, le=100.0)

    # Quality metadata (required for gate validation)
    quality_score: float = Field(..., ge=0.0, le=1.0)
    lighting_score: float | None = Field(default=None, ge=0.0, le=1.0)
    motion_score: float | None = Field(default=None, ge=0.0, le=1.0)
    face_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    audio_snr_db: float | None = Field(default=None)

    flags: list[str] = Field(default_factory=list)

    @field_validator("flags")
    @classmethod
    def validate_flags(cls, v: list[str]) -> list[str]:
        allowed = {
            "low_lighting",
            "motion_detected",
            "face_not_detected",
            "high_noise",
            "partial_scan",
        }
        for flag in v:
            if flag not in allowed:
                raise ValueError(f"Unknown flag: {flag}. Allowed: {allowed}")
        return v


class ScanSessionResponse(BaseModel):
    id: str
    user_id: str
    status: str
    device_model: str | None
    app_version: str | None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ScanResultResponse(BaseModel):
    id: str
    session_id: str
    user_id: str

    # Wellness indicators
    hr_bpm: float | None
    hrv_ms: float | None
    respiratory_rate: float | None
    voice_jitter_pct: float | None
    voice_shimmer_pct: float | None

    # Quality
    quality_score: float
    flags: list[str]

    # Trend — allowed: "consider_lab_followup" | null
    # Never diagnostic language
    trend_alert: Literal["consider_lab_followup"] | None

    created_at: datetime

    model_config = {"from_attributes": True}


class ScanSessionWithResult(BaseModel):
    session: ScanSessionResponse
    result: ScanResultResponse | None

    model_config = {"from_attributes": True}


class ScanHistoryItem(BaseModel):
    session: ScanSessionResponse
    result: ScanResultResponse | None
    # Trend delta vs prior 7-day average (None if insufficient history)
    hr_trend_delta: float | None = None
    hrv_trend_delta: float | None = None

    model_config = {"from_attributes": True}


class ScanHistoryResponse(BaseModel):
    items: list[ScanHistoryItem]
    total: int
    page: int
    page_size: int
