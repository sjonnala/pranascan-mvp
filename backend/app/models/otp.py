"""OTP model — short-lived hashed one-time passwords for phone verification."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OTPRequest(Base):
    """
    Stores a hashed OTP for phone verification.

    - OTP is never stored in plaintext; only a bcrypt hash.
    - Each row has a 10-minute TTL (expires_at).
    - failed_attempts tracks consecutive failures for rate limiting.
    - consumed_at is set once the OTP is successfully verified.
    """

    __tablename__ = "otp_requests"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    phone_e164: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    otp_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=timezone.utc),
        nullable=False,
    )
