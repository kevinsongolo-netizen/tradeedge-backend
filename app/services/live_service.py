"""Live MT5 feed service (Sprint 14).

Unlike most Chart Analysis Engine services, this one IS stateful — it
persists the latest ingested analysis per (user, symbol, timeframe) in
``live_snapshots`` so the website's Chart Analysis Engine can display
fresh data without the user re-pasting candles. Reuses ``ChartService.
full_analysis_from_candles()`` for the actual Level 1/2/3 computation;
this class only adds the persistence layer on top — no engine code was
touched to build this.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.live_snapshot_repo import LiveSnapshotRepository
from app.errors import NotFoundError
from app.services.chart_service import ChartService


class LiveFeedService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = LiveSnapshotRepository(session)
        self.chart_service = ChartService()

    async def ingest(
        self, user_id: int, symbol: str, timeframe: str, candles: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        result = await self.chart_service.full_analysis_from_candles(candles, **kwargs)
        await self.repo.upsert(
            user_id,
            symbol,
            timeframe,
            {
                "analysis": result["analysis"],
                "validation": result["validation"],
                "coach": result["coach"],
                "multi_timeframe": result.get("multi_timeframe"),
            },
        )
        await self.session.commit()
        return result

    async def latest(self, user_id: int, symbol: str, timeframe: str) -> dict[str, Any]:
        row = await self.repo.get(user_id, symbol, timeframe)
        if row is None:
            raise NotFoundError(
                f"No live data yet for {symbol} {timeframe}. Make sure your MT5 EA is "
                "attached and running, and that it's pushed at least one update."
            )
        return {
            "symbol": row.symbol,
            "timeframe": row.timeframe,
            "analysis": row.analysis,
            "validation": row.validation,
            "coach": row.coach,
            "multi_timeframe": row.multi_timeframe,
            "updated_at": row.updated_at,
        }
