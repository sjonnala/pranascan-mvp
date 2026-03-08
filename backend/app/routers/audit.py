"""Audit Log API router — read-only access to immutable audit trail."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit import AuditLog
from app.schemas.audit import AuditLogListResponse, AuditLogResponse

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("/logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    user_id: str | None = Query(default=None, description="Filter by user ID"),
    action: str | None = Query(default=None, description="Filter by action prefix"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> AuditLogListResponse:
    """
    List immutable audit log entries.
    Supports filtering by user_id and action prefix.
    Results are ordered newest-first.
    """
    offset = (page - 1) * page_size

    base_filter = []
    if user_id:
        base_filter.append(AuditLog.user_id == user_id)
    if action:
        base_filter.append(AuditLog.action.startswith(action))

    count_stmt = select(func.count(AuditLog.id)).where(*base_filter)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    logs_stmt = (
        select(AuditLog)
        .where(*base_filter)
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    logs_result = await db.execute(logs_stmt)
    logs = logs_result.scalars().all()

    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )
