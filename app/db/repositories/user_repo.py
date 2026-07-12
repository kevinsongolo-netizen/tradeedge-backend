"""Repository for ``users``.

All SQL for the ``User`` model lives here — services never see
SQLAlchemy directly (Section 5.1 of the architecture spec).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User


class UserRepository:
    """Data access for ``User`` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        """Returns the user row, or ``None`` if it doesn't exist."""
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def ensure_seed_user(self) -> User:
        """Idempotently ensures the Sprint-6 seeded user (``id=1``,
        ``local@tradeedge.ai``) exists. Used by ``scripts/seed_dev.py``
        and by the test fixtures — the Alembic migration also seeds
        this row directly via SQL for a clean production bootstrap."""
        existing = await self.get_by_id(1)
        if existing is not None:
            return existing
        user = User(id=1, email="local@tradeedge.ai", display_name="Local Trader")
        self.session.add(user)
        await self.session.flush()
        return user
