"""Infrastructure bootstrap helpers for startup and local schema setup."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.database import AsyncSessionLocal, async_transaction_scope, create_all_tables
from app.models import BetaInvite, register_models


async def seed_beta_invite_if_configured(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """Create a reusable invite when a local/dev seed code is configured."""
    if not settings.beta_seed_invite_code:
        return

    code = settings.beta_seed_invite_code.strip().upper()
    if not code:
        return

    factory = session_factory or AsyncSessionLocal
    async with async_transaction_scope(factory) as db:
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


async def bootstrap_application_state() -> None:
    """Initialize schema/bootstrap state required during application startup."""
    register_models()

    # Keep Alembic as the default schema manager. AUTO_CREATE_TABLES is an explicit
    # escape hatch for throwaway local databases only.
    if settings.auto_create_tables:
        if settings.environment == "production":
            raise RuntimeError("AUTO_CREATE_TABLES must remain disabled in production.")
        await create_all_tables()

    await seed_beta_invite_if_configured()
