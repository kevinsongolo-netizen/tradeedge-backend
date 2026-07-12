"""Per-request DB session plumbing.

Provides the FastAPI dependency that hands each request its own
``AsyncSession`` (opened, yielded, then closed — with rollback on
exception), plus small helpers used at startup (and in tests) to verify
the configured ``DATABASE_URL`` is reachable and that Alembic
migrations are at head.
"""
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_engine, get_sessionmaker


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: ``Depends(get_db_session)``.

    No routes use this yet — Step 2 scope is the engine/session plumbing
    only (no models, no CRUD routes). It's here so Step 3's routers can
    start depending on it immediately without touching this file again.
    """
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def check_database_connection() -> bool:
    """Opens a real connection through the configured engine and runs
    ``SELECT 1`` to confirm ``DATABASE_URL`` is reachable and the driver
    is correctly installed.

    Raises whatever the underlying driver raises on failure (e.g.
    ``OperationalError``) — callers decide whether that should be fatal.
    Never called from a hot request path; only at startup and by tests.
    """
    engine = get_engine()
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return True


async def check_migrations_at_head() -> tuple[bool, str | None]:
    """Compares the DB's ``alembic_version`` row against the latest
    revision script on disk. Used by ``/readyz`` so a container that
    booted against a stale/un-migrated database reports "not ready"
    instead of silently serving traffic against the wrong schema.

    Returns ``(at_head, current_revision)``. If the ``alembic_version``
    table doesn't exist yet (schema never migrated), returns
    ``(False, None)`` rather than raising.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    engine = get_engine()
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            row = result.first()
            current = row[0] if row else None
    except Exception:
        return False, None

    config = Config()
    config.set_main_option("script_location", "alembic")
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()
    return current == head, current
