"""PranaScan FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import create_all_tables
from app.middleware.audit_log import audit_log_middleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.timing import TimingMiddleware
from app.models import abha as _abha_models  # noqa: F401 — register tables with Base.metadata
from app.routers import abha, agent, audit, auth, consent, scan, vitality_report


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown lifecycle."""
    # In dev/test, auto-create tables. Production uses Alembic migrations.
    if settings.environment in ("development", "test"):
        await create_all_tables()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "PranaScan wellness screening API. "
        "Outputs are wellness indicators only — not diagnostic values. "
        "Always consult a qualified healthcare professional."
    ),
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
)

# CORS — restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment != "production" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Timing middleware — outermost so it measures total request time
app.add_middleware(TimingMiddleware)

# Security headers middleware — wraps audit log middleware
app.add_middleware(SecurityHeadersMiddleware)

# Audit logging middleware
app.add_middleware(BaseHTTPMiddleware, dispatch=audit_log_middleware)

# Routers
API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(consent.router, prefix=API_PREFIX)
app.include_router(scan.router, prefix=API_PREFIX)
app.include_router(audit.router, prefix=API_PREFIX)
app.include_router(vitality_report.router, prefix=API_PREFIX)
app.include_router(abha.router, prefix=API_PREFIX)
app.include_router(agent.router, prefix=API_PREFIX)


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    return {"status": "ok", "version": settings.version, "environment": settings.environment}


@app.get("/", tags=["Root"])
async def root() -> dict:
    return {
        "service": settings.app_name,
        "version": settings.version,
        "disclaimer": (
            "PranaScan provides wellness indicators only. "
            "This is not a medical device and does not provide diagnoses. "
            "Consult a qualified healthcare professional for any health concerns."
        ),
        "docs": "/docs",
    }
