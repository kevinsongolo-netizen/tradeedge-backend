"""Repository for ``ml_exports`` — audit log of dataset export runs."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ml_export import MLExport


class MLExportRepository:
    """Data access for ``MLExport`` audit rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, user_id: int, data: dict[str, Any]) -> MLExport:
        row = MLExport(user_id=user_id, **data)
        self.session.add(row)
        await self.session.flush()
        return row
