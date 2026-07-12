"""Statistics Service — Section 5.2's ``summary``, ``charts``,
``strategy_health``, ``setups``, ``mistakes``.

Loads a user's journal history (optionally filtered by date range /
pair / session, per Section 4.5), then runs the relevant pure engines.
Results are cached per user behind a fingerprint of
``(user_id, len(trades), max(updated_at), filters)`` so repeated
dashboard polling doesn't re-aggregate the whole journal every time
(Section 5.3).
"""
from __future__ import annotations

from datetime import date as date_
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.trade_repo import TradeRepository
from app.engines.mistake_engine import analyze_mistakes
from app.engines.setup_engine import analyze_setups
from app.engines.statistics_engine import build_chart_data, compute_statistics
from app.engines.strategy_health_engine import compute_strategy_health
from app.services.cache import stats_cache


class StatsFilters:
    def __init__(
        self,
        pair: str | None = None,
        session_name: str | None = None,
        date_from: date_ | None = None,
        date_to: date_ | None = None,
    ) -> None:
        self.pair = pair.upper() if pair else None
        self.session_name = session_name
        self.date_from = date_from
        self.date_to = date_to

    def fingerprint_suffix(self) -> str:
        return f"{self.pair}|{self.session_name}|{self.date_from}|{self.date_to}"

    def apply(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = entries
        if self.pair:
            rows = [e for e in rows if e.get("pair") == self.pair]
        if self.session_name:
            rows = [e for e in rows if e.get("session") == self.session_name]
        if self.date_from:
            rows = [e for e in rows if e.get("date") and e["date"] >= self.date_from.isoformat()]
        if self.date_to:
            rows = [e for e in rows if e.get("date") and e["date"] <= self.date_to.isoformat()]
        return rows


class StatsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.trade_repo = TradeRepository(session)

    async def _fingerprint(self, user_id: int, filters: StatsFilters) -> str:
        count = await self.trade_repo.count(user_id)
        max_updated = await self.trade_repo.max_updated_at(user_id)
        return f"{user_id}|{count}|{max_updated}|{filters.fingerprint_suffix()}"

    async def _filtered_history(self, user_id: int, filters: StatsFilters) -> list[dict[str, Any]]:
        history = [t.to_engine_dict() for t in await self.trade_repo.list_all(user_id)]
        return filters.apply(history)

    async def summary(self, user_id: int, filters: StatsFilters) -> dict:
        fingerprint = await self._fingerprint(user_id, filters)

        async def compute() -> dict:
            entries = await self._filtered_history(user_id, filters)
            stats = compute_statistics(entries)
            setups = analyze_setups(entries)
            top = setups["top"]
            stats["bestSetup"] = setups["bestSetup"]
            worst_poi_candidates = [
                (key, val) for key, val in stats["byPOI"].items() if val["totalTrades"] >= 1
            ]
            stats["worstSetup"] = (
                min(worst_poi_candidates, key=lambda kv: kv[1]["winRate"])[0] if worst_poi_candidates else None
            )
            return stats

        return await stats_cache.get_or_set(("summary", user_id), fingerprint, compute)

    async def charts(self, user_id: int, filters: StatsFilters) -> dict:
        fingerprint = await self._fingerprint(user_id, filters)

        async def compute() -> dict:
            entries = await self._filtered_history(user_id, filters)
            return build_chart_data(entries)

        return await stats_cache.get_or_set(("charts", user_id), fingerprint, compute)

    async def strategy_health(self, user_id: int, filters: StatsFilters) -> dict:
        fingerprint = await self._fingerprint(user_id, filters)

        async def compute() -> dict:
            entries = await self._filtered_history(user_id, filters)
            return compute_strategy_health(entries)

        return await stats_cache.get_or_set(("health", user_id), fingerprint, compute)

    async def setups(self, user_id: int, filters: StatsFilters) -> dict:
        fingerprint = await self._fingerprint(user_id, filters)

        async def compute() -> dict:
            entries = await self._filtered_history(user_id, filters)
            return analyze_setups(entries)

        return await stats_cache.get_or_set(("setups", user_id), fingerprint, compute)

    async def mistakes(self, user_id: int, filters: StatsFilters) -> dict:
        fingerprint = await self._fingerprint(user_id, filters)

        async def compute() -> dict:
            entries = await self._filtered_history(user_id, filters)
            return analyze_mistakes(entries)

        return await stats_cache.get_or_set(("mistakes", user_id), fingerprint, compute)

    async def raw_history(self, user_id: int, filters: StatsFilters) -> list[dict[str, Any]]:
        """Exposed for CoachService, which needs the same filtered
        entries plus the derived stats/setup/mistake/health objects."""
        return await self._filtered_history(user_id, filters)
