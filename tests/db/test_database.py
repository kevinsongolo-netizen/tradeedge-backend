"""Step 2 acceptance tests: async engine, session factory, connectivity,
and env-var-driven configuration. No ORM models exist yet, so these tests
only exercise the engine/session plumbing itself — not any table.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import Settings
from app.db.base import Base
from app.db.database import get_engine, get_sessionmaker
from app.db.session import check_database_connection, get_db_session


def test_database_url_configured_from_settings():
    """The engine is built from Settings.database_url, which itself comes
    from the DATABASE_URL env var (see app/config.py)."""
    settings = Settings()
    assert settings.database_url  # non-empty
    assert "sqlite" in settings.database_url or "postgresql" in settings.database_url


def test_settings_reads_database_url_from_env(monkeypatch):
    """DATABASE_URL is read from the environment, not hardcoded."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./data/test_env_override.db")
    settings = Settings()
    assert settings.database_url == "sqlite+aiosqlite:///./data/test_env_override.db"


def test_get_engine_returns_async_engine():
    engine = get_engine()
    assert isinstance(engine, AsyncEngine)


def test_get_engine_is_cached_singleton():
    assert get_engine() is get_engine()


def test_get_sessionmaker_is_cached_singleton():
    assert get_sessionmaker() is get_sessionmaker()


def test_declarative_base_has_naming_convention():
    """Base.metadata carries the shared naming convention every future
    model's table will use — this is what Step 2 sets up ahead of
    Step 3's models."""
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"


@pytest.mark.asyncio
async def test_check_database_connection_succeeds():
    """The core Step 2 deliverable: the configured DATABASE_URL is
    actually reachable."""
    assert await check_database_connection() is True


@pytest.mark.asyncio
async def test_session_factory_produces_working_async_session():
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        assert isinstance(session, AsyncSession)
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1


@pytest.mark.asyncio
async def test_get_db_session_dependency_yields_usable_session():
    """Exercises the exact generator FastAPI will call via
    ``Depends(get_db_session)`` once Step 3 routers exist."""
    gen = get_db_session()
    session = await gen.__anext__()
    try:
        assert isinstance(session, AsyncSession)
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
    finally:
        # Drain the generator so its context managers close cleanly.
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
