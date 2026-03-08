"""Pydantic v2 schemas for audit log endpoints."""

from datetime import datetime

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: str
    user_id: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    http_method: str
    http_path: str
    http_status: int | None
    duration_ms: int | None
    ip_address: str | None
    detail: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
