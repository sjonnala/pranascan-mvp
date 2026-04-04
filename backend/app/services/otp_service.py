"""OTP service — generation, hashing, verification, and rate limiting."""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.otp import OTPRequest
from app.models.user import User

logger = logging.getLogger(__name__)

OTP_LENGTH = 6
OTP_TTL_MINUTES = 10
MAX_FAILED_ATTEMPTS = 5


def generate_otp() -> str:
    """Generate a cryptographically random 6-digit OTP."""
    return "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))


def hash_otp(otp: str) -> str:
    """Hash an OTP using HMAC-SHA256 with the app secret key."""
    return hmac.new(
        settings.secret_key.encode(), otp.encode(), hashlib.sha256
    ).hexdigest()


def verify_otp_hash(otp: str, otp_hash: str) -> bool:
    """Verify an OTP against its HMAC-SHA256 hash (constant-time comparison)."""
    return hmac.compare_digest(hash_otp(otp), otp_hash)


async def create_otp(db: AsyncSession, phone_e164: str) -> str:
    """
    Create a new OTP for the given phone number.

    Returns the plaintext OTP (for delivery to the user).
    The stored copy is hashed — plaintext is never persisted.
    """
    otp = generate_otp()

    otp_request = OTPRequest(
        phone_e164=phone_e164,
        otp_hash=hash_otp(otp),
        expires_at=datetime.now(tz=timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES),
    )
    db.add(otp_request)
    await db.flush()

    # Log delivery stub — injectable interface for future SMS provider
    logger.info("OTP delivery stub: phone=%s otp_id=%s", phone_e164, otp_request.id)
    # DECISION: OTP value is logged at DEBUG only, never at INFO+
    logger.debug("OTP value (dev only): %s", otp)

    return otp


async def verify_otp(
    db: AsyncSession, phone_e164: str, otp: str
) -> tuple[bool, str]:
    """
    Verify an OTP for the given phone number.

    Returns (success: bool, message: str).
    On success, the OTP is consumed and cannot be reused.
    """
    now = datetime.now(tz=timezone.utc)

    # Find the most recent unconsumed OTP for this phone
    stmt = (
        select(OTPRequest)
        .where(
            OTPRequest.phone_e164 == phone_e164,
            OTPRequest.consumed_at.is_(None),
        )
        .order_by(OTPRequest.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    otp_record = result.scalar_one_or_none()

    if otp_record is None:
        return False, "No pending OTP found. Please request a new one."

    # Check rate limit
    if otp_record.failed_attempts >= MAX_FAILED_ATTEMPTS:
        return False, "Too many failed attempts. Please request a new OTP."

    # Check expiry — handle both naive (SQLite) and aware (Postgres) datetimes
    expires_at = otp_record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        return False, "OTP has expired. Please request a new one."

    # Verify the OTP hash
    if not verify_otp_hash(otp, otp_record.otp_hash):
        otp_record.failed_attempts += 1
        await db.flush()
        remaining = MAX_FAILED_ATTEMPTS - otp_record.failed_attempts
        if remaining <= 0:
            return False, "Too many failed attempts. Please request a new OTP."
        return False, "Invalid OTP."

    # Success — consume the OTP
    otp_record.consumed_at = now
    await db.flush()

    return True, "OTP verified successfully."


async def get_or_create_user(db: AsyncSession, phone_e164: str) -> User:
    """
    Upsert a user by phone number.

    If the phone is already registered, return the existing user.
    Otherwise, create a new user (first login).
    """
    stmt = select(User).where(User.phone_e164 == phone_e164)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is not None:
        return user

    user = User(phone_e164=phone_e164)
    db.add(user)
    await db.flush()
    logger.info("New user created: user_id=%s", user.id)
    return user
