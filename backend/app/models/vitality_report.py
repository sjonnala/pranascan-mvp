"""Vitality report storage model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class VitalityReport(Base):
    __tablename__ = "vitality_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Report window
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scan_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Metric averages (current week)
    avg_hr_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_hrv_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_respiratory_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_voice_jitter_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_voice_shimmer_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Week-over-week deltas
    delta_hr_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta_hrv_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Supplementary indicators (latest from the period)
    latest_vascular_age_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    latest_vascular_age_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    latest_anemia_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    latest_anemia_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Rendered text summary
    summary_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
