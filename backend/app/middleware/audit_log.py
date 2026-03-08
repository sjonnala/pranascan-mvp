"""
Audit logging middleware.

Auto-logs every HTTP request to the immutable audit_logs table.
Implemented as a BaseHTTPMiddleware dispatch function.
"""

import time

from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from app.database import AsyncSessionLocal
from app.models.audit import AuditLog


async def audit_log_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """
    Starlette BaseHTTPMiddleware dispatch function.
    Appends an AuditLog row for every request/response cycle.
    Audit failures must never break the main request.
    """
    start_time = time.monotonic()
    response = await call_next(request)
    duration_ms = int((time.monotonic() - start_time) * 1000)

    path = request.url.path

    # Skip health checks and audit endpoint itself to reduce noise
    if path in ("/health", "/") or path.startswith("/api/v1/audit"):
        return response

    user_id: str | None = None
    if hasattr(request.state, "user_id"):
        user_id = request.state.user_id

    ip_address = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else None)
    )

    action = f"{request.method}:{path}"

    try:
        async with AsyncSessionLocal() as db:
            entry = AuditLog(
                user_id=user_id,
                action=action,
                http_method=request.method,
                http_path=path,
                http_status=response.status_code,
                duration_ms=duration_ms,
                ip_address=ip_address,
                user_agent=request.headers.get("user-agent"),
            )
            db.add(entry)
            await db.commit()
    except Exception:
        # Audit failures must not break the main request
        pass

    return response


# Keep a class-based wrapper for backwards compat with existing import in main.py
class AuditLogMiddleware:
    """Thin wrapper so main.py can still reference this class."""

    def __init__(self, app):
        self.app = app
        self.dispatch_func = audit_log_middleware
