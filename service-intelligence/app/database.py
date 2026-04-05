"""SQLAlchemy database setup and transaction helpers."""

from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@asynccontextmanager
async def async_transaction_scope(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> AsyncIterator[AsyncSession]:
    """
    Yield an async session and own the commit/rollback boundary.

    This is the standard transaction entry point for request dependencies,
    startup tasks, middleware, and background jobs that open their own
    async session.
    """
    factory = session_factory or AsyncSessionLocal
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@contextmanager
def transaction_scope(session: Session) -> Iterator[Session]:
    """
    Own one sync transaction on a caller-provided Session.

    Used by sync job-style services that intentionally process work in
    explicit transaction chunks.
    """
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async DB session."""
    async with async_transaction_scope(AsyncSessionLocal) as session:
        yield session


async def create_all_tables() -> None:
    """Create all tables for tests or explicit local bootstrap workflows."""
    from app.models import register_models

    register_models()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_all_tables() -> None:
    """Drop all tables (used in tests only)."""
    from app.models import register_models

    register_models()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
