"""Scan session and result models."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SessionStatus(str, Enum):
    INITIATED = "initiated"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"  # Quality gate failure


class ScanSession(Base):
    __tablename__ = "scan_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=SessionStatus.INITIATED)
    device_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScanResult(Base):
    """
    Stores anonymised wellness metric snapshots.
    Raw video/audio never reaches this table — edge processing only.
    """

    __tablename__ = "scan_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, unique=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Wellness indicators — NOT diagnostic values
    hr_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    hrv_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    respiratory_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    voice_jitter_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    voice_shimmer_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Quality metadata
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    lighting_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    motion_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    face_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    audio_snr_db: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Flags and trend (list of strings, nullable string)
    flags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Allowed values: "consider_lab_followup" | null — never diagnostic language
    trend_alert: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
