"""Pydantic v2 schemas for compute-only scan evaluation payloads."""

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class FrameSampleSchema(BaseModel):
    """Single video frame colour channel means (sent instead of raw pixels)."""

    t_ms: float = Field(..., ge=0, description="Timestamp from scan start in milliseconds")
    r_mean: float = Field(..., ge=0.0, le=255.0)
    g_mean: float = Field(..., ge=0.0, le=255.0)
    b_mean: float = Field(..., ge=0.0, le=255.0)


class ScanType(StrEnum):
    STANDARD = "standard"
    DEEP_DIVE = "deep_dive"


class ScanResultSubmit(BaseModel):
    """
    Wellness indicator values submitted after a scan session.

    Raw video/audio is never sent through the product-facing app flow. The
    internal compute contract can still accept frame/audio-derived samples and
    optional media bytes for server-side fallback processing.
    These are wellness indicators, not diagnostic values.
    """

    scan_type: ScanType = Field(
        default=ScanType.STANDARD,
        description="Routes the scan to either selfie POS processing or contact morphology processing.",
    )

    frame_data: list[FrameSampleSchema] | None = Field(
        default=None,
        description="Per-frame RGB means for server-side rPPG. Overrides client-computed values.",
        max_length=4000,  # ~60s at 60fps ceiling with small headroom
    )

    audio_samples: list[float] | None = Field(
        default=None,
        description="Normalised audio amplitude samples (4410 Hz) for voice DSP.",
        max_length=22_050,  # 5s at 4410 Hz
    )

    hr_bpm: float | None = Field(default=None, ge=30.0, le=220.0)
    hrv_ms: float | None = Field(default=None, ge=0.0, le=500.0)
    respiratory_rate: float | None = Field(default=None, ge=4.0, le=60.0)
    voice_jitter_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    voice_shimmer_pct: float | None = Field(default=None, ge=0.0, le=100.0)

    quality_score: float = Field(..., ge=0.0, le=1.0)
    lighting_score: float | None = Field(default=None, ge=0.0, le=1.0)
    motion_score: float | None = Field(default=None, ge=0.0, le=1.0)
    face_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    audio_snr_db: float | None = Field(default=None)

    flags: list[str] = Field(default_factory=list)

    user_height_cm: float | None = Field(default=None, ge=100.0, le=250.0)

    frame_r_mean: float | None = Field(default=None, ge=0.0, le=255.0)
    frame_g_mean: float | None = Field(default=None, ge=0.0, le=255.0)
    frame_b_mean: float | None = Field(default=None, ge=0.0, le=255.0)

    @field_validator("flags")
    @classmethod
    def validate_flags(cls, v: list[str]) -> list[str]:
        allowed = {
            "low_lighting",
            "borderline_lighting",
            "motion_detected",
            "face_not_detected",
            "partial_occlusion_suspected",
            "poor_thumb_contact",
            "borderline_thumb_contact",
            "high_noise",
            "borderline_noise",
            "accented_vowel_accommodated",
            "partial_scan",
        }
        for flag in v:
            if flag not in allowed:
                raise ValueError(f"Unknown flag: {flag}. Allowed: {allowed}")
        return v
