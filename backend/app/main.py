"""PranaScan FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import AsyncSessionLocal, create_all_tables
from app.middleware.audit_log import audit_log_middleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.timing import TimingMiddleware
from app.models import (
    abha as _abha_models,  # noqa: F401 — register tables with Base.metadata
)
from app.models import (
    beta as _beta_models,  # noqa: F401 — register tables with Base.metadata
)
from app.models import (
    feedback as _feedback_models,  # noqa: F401 — register tables with Base.metadata
)
from app.models import (
    otp as _otp_models,  # noqa: F401 — register tables with Base.metadata
)
from app.models import (
    user as _user_models,  # noqa: F401 — register tables with Base.metadata
)
from app.models.beta import BetaInvite
from app.routers import abha, agent, audit, auth, beta, consent, feedback, scan, vitality_report


async def seed_beta_invite_if_configured() -> None:
    """Create a reusable invite when a local/dev seed code is configured."""
    if not settings.beta_seed_invite_code:
        return

    code = settings.beta_seed_invite_code.strip().upper()
    if not code:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(BetaInvite).where(BetaInvite.code == code))
        invite = result.scalar_one_or_none()
        if invite is not None:
            return

        db.add(
            BetaInvite(
                code=code,
                cohort_name=settings.beta_seed_invite_cohort,
                max_redemptions=settings.beta_seed_invite_max_redemptions,
            )
        )
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown lifecycle."""
    # Keep Alembic as the default schema manager. AUTO_CREATE_TABLES is an explicit
    # escape hatch for throwaway local databases only.
    if settings.auto_create_tables:
        if settings.environment == "production":
            raise RuntimeError("AUTO_CREATE_TABLES must remain disabled in production.")
        await create_all_tables()
    await seed_beta_invite_if_configured()
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
app.include_router(feedback.router, prefix=API_PREFIX)
app.include_router(beta.router, prefix=API_PREFIX)


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
