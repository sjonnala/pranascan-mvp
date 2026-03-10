"""
Security response headers middleware.

Adds standard defensive HTTP headers to every API response.
Strict-Transport-Security is only emitted in production (HTTPS only).
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # Disable legacy XSS filter (modern browsers ignore it; no harm)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Do not send referrer on cross-origin requests
        response.headers["Referrer-Policy"] = "no-referrer"
        # No caching of API responses
        response.headers["Cache-Control"] = "no-store"
        # Permissions policy: deny access to camera/mic from browser context
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # HSTS — only in production (requires HTTPS)
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        # Remove server header if present (don't leak server info)
        if "server" in response.headers:
            del response.headers["server"]

        return response
