"""Repository for ``ai_analyses``.

Analysis rows are append-only — one row per ``analyze`` call, used to
build a per-trade scoring history (``GET /ai/trades/{id}/analyses``)
and as the versioned source of truth behind the cached score columns
on ``trades``.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ai_analysis import AIAnalysis


class AnalysisRepository:
    """Data access for ``AIAnalysis`` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, user_id: int, trade_id: str, data: dict[str, Any]) -> AIAnalysis:
        analysis = AIAnalysis(user_id=user_id, trade_id=trade_id, **data)
        self.session.add(analysis)
        await self.session.flush()
        return analysis

    async def list_for_trade(
        self, user_id: int, trade_id: str, limit: int = 50
    ) -> list[AIAnalysis]:
        result = await self.session.execute(
            select(AIAnalysis)
            .where(AIAnalysis.trade_id == trade_id, AIAnalysis.user_id == user_id)
            .order_by(AIAnalysis.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
