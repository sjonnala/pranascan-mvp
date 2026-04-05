"""Infrastructure bootstrap helpers for startup and local schema setup."""

from app.config import settings
from app.database import create_all_tables
from app.models import register_models


async def bootstrap_application_state() -> None:
    """Initialize schema/bootstrap state required during application startup."""
    register_models()

    # Keep Alembic as the default schema manager. AUTO_CREATE_TABLES is an explicit
    # escape hatch for throwaway local databases only.
    if settings.auto_create_tables:
        if settings.environment == "production":
            raise RuntimeError("AUTO_CREATE_TABLES must remain disabled in production.")
        await create_all_tables()
