"""Async SQLAlchemy engine + session factory.

Single source of truth for how the app talks to the database. The
connection string comes entirely from ``app.config.Settings.database_url``
(environment variable ``DATABASE_URL`` — see ``.env.example``), so moving
from the local SQLite file to Postgres in another environment is a
one-line env-var change (``sqlite+aiosqlite:///...`` ->
``postgresql+asyncpg://...``), never a code change.

Step 2 scope: engine + session factory only. No models (Step 3+), no
Alembic (separate step), no routers depending on the session yet.
"""
from functools import lru_cache
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


def _engine_kwargs(database_url: str) -> dict[str, Any]:
    """Backend-specific engine tuning.

    SQLite (dev, via aiosqlite) is a local file with a single writer —
    there's no connection pool worth pre-pinging. Any other backend
    (Postgres via asyncpg in staging/prod) gets ``pool_pre_ping`` so a
    dropped/stale connection is detected and transparently replaced
    instead of surfacing as a confusing query-time error.
    """
    if database_url.startswith("sqlite"):
        return {"echo": False}
    return {"echo": False, "pool_pre_ping": True}


@lru_cache
def get_engine() -> AsyncEngine:
    """Cached engine singleton — one engine (and its connection pool) per
    process, matching the caching style of ``get_settings()``."""
    settings = get_settings()
    return create_async_engine(settings.database_url, **_engine_kwargs(settings.database_url))


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Cached async session factory bound to the cached engine.

    ``expire_on_commit=False`` so ORM objects returned from a service
    stay usable (e.g. for serialization into a Pydantic schema) after
    the session's transaction commits, without triggering a lazy-load.
    """
    return async_sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)


async def dispose_engine() -> None:
    """Closes the engine's connection pool. Called on app shutdown, and
    useful in tests to release the cached engine between runs."""
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
