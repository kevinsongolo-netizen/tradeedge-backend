"""Repository for ``ml_models`` — Sprint 7's trained-model registry.

The table itself (``app/db/models/ml_export.py::MLModel``) was created
empty in Sprint 6 as a placeholder specifically for this sprint; this
file is the first thing that actually reads/writes it.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ml_export import MLModel


class MLModelRepository:
    """Data access for ``MLModel`` rows. Exactly one row per user may
    have ``is_active=True`` at a time — ``insert_and_activate`` enforces
    that by deactivating every other row for the user in the same
    transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self, user_id: int) -> list[MLModel]:
        result = await self.session.execute(
            select(MLModel).where(MLModel.user_id == user_id).order_by(MLModel.id.desc())
        )
        return list(result.scalars().all())

    async def get_active(self, user_id: int) -> MLModel | None:
        result = await self.session.execute(
            select(MLModel).where(MLModel.user_id == user_id, MLModel.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def insert_and_activate(self, user_id: int, data: dict[str, Any]) -> MLModel:
        await self.session.execute(
            update(MLModel)
            .where(MLModel.user_id == user_id, MLModel.is_active.is_(True))
            .values(is_active=False)
        )
        row = MLModel(user_id=user_id, is_active=True, **data)
        self.session.add(row)
        await self.session.flush()
        return row
