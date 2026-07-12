"""Shared pytest fixtures.

Test isolation strategy: ``DATABASE_URL`` (and ``EXPORT_DIR``) are
pointed at temp paths *before* anything under ``app`` is imported, so
the lru_cache'd ``get_settings()``/``get_engine()``/``get_sessionmaker()``
singletons are bound to the test database for the whole session — no
cache-clearing gymnastics needed. Each test function gets a clean
database (all tables wiped, seed user re-inserted) via the autouse
``_clean_db`` fixture, so tests can run in any order without leaking
state into each other.
"""
import asyncio
import os
import tempfile
from pathlib import Path

_TEST_DB_FILE = tempfile.NamedTemporaryFile(prefix="tradeedge_test_", suffix=".db", delete=False)
_TEST_DB_FILE.close()
_TEST_EXPORT_DIR = tempfile.mkdtemp(prefix="tradeedge_test_exports_")
_TEST_MODELS_DIR = tempfile.mkdtemp(prefix="tradeedge_test_models_")  # Sprint 7

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_FILE.name}"
os.environ["EXPORT_DIR"] = _TEST_EXPORT_DIR
os.environ["MODELS_DIR"] = _TEST_MODELS_DIR  # Sprint 7 — joblib artifacts, isolated per test session
os.environ["APP_ENV"] = "dev"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.base import Base
from app.db.database import get_engine
from app.db.repositories import UserRepository
from app.db.database import get_sessionmaker
from app.main import app

SEED_USER_ID = 1
SEED_USER_EMAIL = "local@tradeedge.ai"


def _run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _create_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _seed_user() -> None:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        await UserRepository(session).ensure_seed_user()
        await session.commit()


async def _wipe_tables() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest.fixture(scope="session", autouse=True)
def _db_schema():
    """Creates every table once for the whole test session."""
    _run_async(_create_schema())
    yield


@pytest.fixture(autouse=True)
def _clean_db(_db_schema):
    """Wipes all rows and re-seeds the default user before every test,
    so tests never see another test's trades."""
    _run_async(_wipe_tables())
    _run_async(_seed_user())
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def user_id() -> int:
    return SEED_USER_ID
