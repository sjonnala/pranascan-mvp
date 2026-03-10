"""ABHA (Ayushman Bharat Health Account) linkage and sync models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AbhaLink(Base):
    """
    Stores ABHA ID linkage for a pseudonymous user.

    Only one active link per user at a time. Relinking replaces the prior record
    (old record gets an unlinked_at timestamp).

    PII note: abha_id is a nationally-issued health identifier. It is stored
    in this table to enable ABDM sync. No raw biometric data is stored here.
    """

    __tablename__ = "abha_links"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # ABHA format: 14-digit, stored as XX-XXXX-XXXX-XXXX string (17 chars)
    abha_id: Mapped[str] = mapped_column(String(20), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    unlinked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AbhaSyncRecord(Base):
    """
    Audit trail of scan result → ABDM Gateway sync attempts.

    One record per (session_id, attempt). Retries produce new records.
    """

    __tablename__ = "abha_sync_records"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    abha_id: Mapped[str] = mapped_column(String(20), nullable=False)
    # "success" | "skipped_disabled" | "skipped_no_link" | "failed"
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    # Sandbox vs live gateway call
    sandbox: Mapped[bool] = mapped_column(default=True, nullable=False)
    # Optional ABDM transaction/reference ID returned by gateway
    gateway_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
