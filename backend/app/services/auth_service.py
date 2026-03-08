"""JWT token creation and validation."""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import ExpiredSignatureError, JWTError, jwt

from app.config import settings

_ALGORITHM = settings.algorithm


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def create_access_token(user_id: str) -> str:
    """Issue a short-lived access token."""
    expire = _now_utc() + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "type": "access",
        "exp": expire,
        "iat": _now_utc(),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Issue a long-lived refresh token (30 days)."""
    expire = _now_utc() + timedelta(days=30)
    payload: dict[str, Any] = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
        "iat": _now_utc(),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    """
    Decode and validate a JWT.

    Returns the payload dict on success, None on any failure
    (expired, tampered, malformed).
    """
    try:
        payload: dict[str, Any] = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
        return payload
    except (JWTError, ExpiredSignatureError):
        return None
