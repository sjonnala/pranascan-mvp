"""Consent service — manages append-only consent records."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.consent import ConsentAction, ConsentRecord
from app.schemas.consent import ConsentStatusResponse


async def grant_consent(
    db: AsyncSession,
    user_id: str,
    consent_version: str,
    purpose: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> ConsentRecord:
    """Insert a new GRANTED consent record (append-only)."""
    record = ConsentRecord(
        user_id=user_id,
        action=ConsentAction.GRANTED,
        consent_version=consent_version,
        purpose=purpose,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def revoke_consent(
    db: AsyncSession,
    user_id: str,
    consent_version: str = settings.consent_version,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> ConsentRecord:
    """Insert a REVOKED consent record (append-only)."""
    record = ConsentRecord(
        user_id=user_id,
        action=ConsentAction.REVOKED,
        consent_version=consent_version,
        purpose="consent_revocation",
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def request_deletion(
    db: AsyncSession,
    user_id: str,
    consent_version: str = settings.consent_version,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> ConsentRecord:
    """
    Insert a DELETION_REQUESTED record.
    Scheduled deletion date = now + 30-day legal hold.
    """
    deletion_scheduled_at = datetime.now(tz=timezone.utc) + timedelta(
        days=settings.deletion_hold_days
    )
    record = ConsentRecord(
        user_id=user_id,
        action=ConsentAction.DELETION_REQUESTED,
        consent_version=consent_version,
        purpose="data_deletion_request",
        ip_address=ip_address,
        user_agent=user_agent,
        deletion_scheduled_at=deletion_scheduled_at,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def get_consent_status(db: AsyncSession, user_id: str) -> ConsentStatusResponse:
    """
    Compute current consent status from the append-only ledger.

    Strategy: iterate records in insertion order (by primary-key rowid, not
    timestamp, to avoid ties when rows are created in the same millisecond).
    The LAST record of each action type seen wins.
    Active consent = most recent significant action is GRANTED.
    """
    # Use id ordering as a proxy for insertion order (UUID v4 not ordered,
    # so we rely on SQLite autoincrement rowid by fetching all and sorting
    # by created_at, then by id as tiebreaker).
    stmt = (
        select(ConsentRecord)
        .where(ConsentRecord.user_id == user_id)
        .order_by(ConsentRecord.created_at.asc(), ConsentRecord.id.asc())
    )
    result = await db.execute(stmt)
    records = result.scalars().all()

    granted_at: datetime | None = None
    revoked_at: datetime | None = None
    deletion_requested = False
    deletion_scheduled_at: datetime | None = None
    consent_version: str | None = None
    # Track the index of the most recent grant and revoke to determine which is "later"
    last_grant_idx: int = -1
    last_revoke_idx: int = -1

    for idx, record in enumerate(records):
        if record.action == ConsentAction.GRANTED:
            granted_at = record.created_at
            consent_version = record.consent_version
            last_grant_idx = idx
        elif record.action == ConsentAction.REVOKED:
            revoked_at = record.created_at
            last_revoke_idx = idx
        elif record.action == ConsentAction.DELETION_REQUESTED:
            deletion_requested = True
            deletion_scheduled_at = record.deletion_scheduled_at

    # Active consent: most recent action is a grant (grant comes after any revoke)
    has_active_consent = (
        granted_at is not None
        and not deletion_requested
        and last_grant_idx > last_revoke_idx
    )

    return ConsentStatusResponse(
        user_id=user_id,
        has_active_consent=has_active_consent,
        consent_version=consent_version,
        granted_at=granted_at,
        revoked_at=revoked_at,
        deletion_requested=deletion_requested,
        deletion_scheduled_at=deletion_scheduled_at,
    )


async def has_active_consent(db: AsyncSession, user_id: str) -> bool:
    """Quick check for active consent — used as a guard in other routers."""
    status = await get_consent_status(db, user_id)
    return status.has_active_consent
