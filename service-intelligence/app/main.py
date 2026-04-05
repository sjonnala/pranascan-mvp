"""PranaScan intelligence-service entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.bootstrap import bootstrap_application_state
from app.config import settings
from app.grpc_runtime import build_grpc_bind_address, start_grpc_server, stop_grpc_server
from app.middleware.audit_log import audit_log_middleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.timing import TimingMiddleware
from app.models import register_models

register_models()


def create_app(
    *,
    enable_grpc: bool | None = None,
) -> FastAPI:
    """Create the intelligence-service ASGI app."""
    grpc_enabled = settings.grpc_enabled if enable_grpc is None else enable_grpc

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application startup / shutdown lifecycle."""
        await bootstrap_application_state()

        grpc_server = None
        grpc_bind_address = None
        if grpc_enabled:
            grpc_bind_address = build_grpc_bind_address()
            grpc_server = await start_grpc_server(grpc_bind_address)

        app.state.grpc_server = grpc_server
        app.state.grpc_enabled = grpc_enabled
        app.state.grpc_bind_address = grpc_bind_address

        try:
            yield
        finally:
            await stop_grpc_server(grpc_server)

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=(
            "PranaScan intelligence service. "
            "This process now exposes internal compute gRPC contracts used by "
            "service-core."
        ),
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
    )

    app.state.grpc_server = None
    app.state.grpc_enabled = grpc_enabled
    app.state.grpc_bind_address = build_grpc_bind_address() if grpc_enabled else None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.environment != "production" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TimingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BaseHTTPMiddleware, dispatch=audit_log_middleware)

    @app.get("/health", tags=["Health"])
    async def health_check(request: Request) -> dict:
        return {
            "status": "ok",
            "version": settings.version,
            "environment": settings.environment,
            "grpc_enabled": request.app.state.grpc_enabled,
        }

    @app.get("/", tags=["Root"])
    async def root(request: Request) -> dict:
        return {
            "service": settings.app_name,
            "version": settings.version,
            "mode": "internal-compute",
            "grpc": {
                "enabled": request.app.state.grpc_enabled,
                "bind_address": request.app.state.grpc_bind_address,
                "services": [
                    "pranapulse.intelligence.scan.v1.ScanIntelligenceService",
                ],
            },
            "docs": app.docs_url,
        }

    return app


app = create_app()
