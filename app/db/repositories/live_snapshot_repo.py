"""Repository for ``live_snapshots`` (Sprint 14 — Live MT5 Feed)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.live_snapshot import LiveSnapshot


class LiveSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int, symbol: str, timeframe: str) -> LiveSnapshot | None:
        result = await self.session.execute(
            select(LiveSnapshot).where(
                LiveSnapshot.user_id == user_id,
                LiveSnapshot.symbol == symbol,
                LiveSnapshot.timeframe == timeframe,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_for_symbol(self, user_id: int, symbol: str) -> LiveSnapshot | None:
        """Sprint 20 -- the repurposed Scanner doesn't care which
        timeframe an EA happens to be pushing a symbol on, only its
        latest live price, so this ignores timeframe and returns
        whichever row for this symbol was updated most recently.
        Case-insensitive: trades store ``pair`` uppercased, but an EA
        may push its ``symbol`` in whatever case the broker uses (e.g.
        "GOLDmicro") -- that difference alone shouldn't hide an alert."""
        result = await self.session.execute(
            select(LiveSnapshot)
            .where(LiveSnapshot.user_id == user_id, func.upper(LiveSnapshot.symbol) == symbol.upper())
            .order_by(LiveSnapshot.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self, user_id: int, symbol: str, timeframe: str, data: dict[str, Any]
    ) -> LiveSnapshot:
        existing = await self.get(user_id, symbol, timeframe)
        if existing is not None:
            for key, value in data.items():
                setattr(existing, key, value)
            await self.session.flush()
            return existing
        row = LiveSnapshot(user_id=user_id, symbol=symbol, timeframe=timeframe, **data)
        self.session.add(row)
        await self.session.flush()
        return row
