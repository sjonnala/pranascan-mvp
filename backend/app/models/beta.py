"""Closed beta invite and enrollment models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BetaInvite(Base):
    """Redeemable invite codes for closed-beta access."""

    __tablename__ = "beta_invites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    cohort_name: Mapped[str] = mapped_column(String(64), nullable=False)
    max_redemptions: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    redemption_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BetaEnrollment(Base):
    """One closed-beta enrollment record per user."""

    __tablename__ = "beta_enrollments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    invite_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    invite_code: Mapped[str] = mapped_column(String(64), nullable=False)
    cohort_name: Mapped[str] = mapped_column(String(64), nullable=False)
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
