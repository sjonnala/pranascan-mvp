"""Request timing middleware — adds X-Process-Time-Ms header to every response."""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

logger = logging.getLogger(__name__)


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
        if elapsed_ms > settings.latency_target_ms:
            logger.warning(
                "slow_request",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "elapsed_ms": elapsed_ms,
                    "target_ms": settings.latency_target_ms,
                },
            )
        return response
