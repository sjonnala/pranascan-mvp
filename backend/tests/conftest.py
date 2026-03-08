"""Pytest fixtures for PranaScan backend tests."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.services.auth_service import create_access_token

# Use an in-memory SQLite database for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_database():
    """Create all tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session():
    """Yield a test database session."""
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """Yield an async HTTP test client with DB override."""

    async def override_get_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# Helpers
TEST_USER_ID = "00000000-0000-0000-0000-000000000001"
TEST_USER_ID_2 = "00000000-0000-0000-0000-000000000002"


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Valid Authorization header for TEST_USER_ID."""
    token = create_access_token(TEST_USER_ID)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_user2() -> dict[str, str]:
    """Valid Authorization header for TEST_USER_ID_2."""
    token = create_access_token(TEST_USER_ID_2)
    return {"Authorization": f"Bearer {token}"}
