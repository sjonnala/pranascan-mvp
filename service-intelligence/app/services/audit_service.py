"""Audit service — write immutable audit log entries."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def log_event(
    db: AsyncSession,
    *,
    action: str,
    http_method: str,
    http_path: str,
    user_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    http_status: int | None = None,
    duration_ms: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    detail: str | None = None,
) -> AuditLog:
    """
    Insert an immutable audit log entry.
    This function must never update or delete existing records.
    """
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        http_method=http_method,
        http_path=http_path,
        http_status=http_status,
        duration_ms=duration_ms,
        ip_address=ip_address,
        user_agent=user_agent,
        detail=detail,
    )
    db.add(entry)
    await db.flush()
    return entry
