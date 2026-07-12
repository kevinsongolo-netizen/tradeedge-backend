"""Repository for ``scoring_weights`` — per-user engine weight overrides."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.weights import ScoringWeights


class WeightsRepository:
    """Data access for the single ``ScoringWeights`` row per user."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int) -> ScoringWeights | None:
        result = await self.session.execute(
            select(ScoringWeights).where(ScoringWeights.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert(self, user_id: int, data: dict[str, Any]) -> ScoringWeights:
        row = await self.get(user_id)
        if row is None:
            row = ScoringWeights(user_id=user_id)
            self.session.add(row)
        for key in ("rule_weights", "execution_weights", "similarity_weights"):
            if key in data and data[key] is not None:
                setattr(row, key, data[key])
        await self.session.flush()
        return row
