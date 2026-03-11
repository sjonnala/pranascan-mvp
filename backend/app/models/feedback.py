"""Scan feedback model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ScanFeedback(Base):
    """Stores post-scan product feedback for a completed scan session."""

    __tablename__ = "scan_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, unique=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    useful_response: Mapped[str] = mapped_column(String(16), nullable=False)
    nps_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
