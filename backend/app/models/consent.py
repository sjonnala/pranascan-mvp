"""Consent models — append-only records."""

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ConsentAction(str, Enum):
    GRANTED = "granted"
    REVOKED = "revoked"
    DELETION_REQUESTED = "deletion_requested"


class ConsentRecord(Base):
    """
    Append-only consent ledger.
    Never UPDATE or DELETE rows — only INSERT new records.
    """

    __tablename__ = "consent_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)  # ConsentAction value
    consent_version: Mapped[str] = mapped_column(String(16), nullable=False)
    purpose: Mapped[str] = mapped_column(String(256), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Python-side default with microsecond precision for reliable ordering in tests
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=timezone.utc),
        nullable=False,
    )
    # For deletion requests: scheduled deletion date (now + 30 days)
    deletion_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Soft-delete flag: set when deletion actually executes
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
