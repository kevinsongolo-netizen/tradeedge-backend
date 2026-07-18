"""Coach Service — Section 5.2's ``insights``.

Builds coaching insights from cached statistics/setup/mistake/health
data (never from hardcoded advice). A 60-second TTL cache sits on top
of the stats fingerprint cache so rapid dashboard polling doesn't
recompute everything (Section 5.3).
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.coach_deep_dive_engine import build_deep_dive
from app.engines.coach_engine import generate_coach_insights
from app.engines.mistake_engine import analyze_mistakes
from app.engines.playbook_engine import build_playbook
from app.engines.setup_engine import analyze_setups
from app.engines.statistics_engine import compute_statistics
from app.engines.strategy_health_engine import compute_strategy_health
from app.services.cache import coach_cache
from app.services.stats_service import StatsFilters, StatsService


class CoachService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.stats_service = StatsService(session)

    async def insights(self, user_id: int, limit: int = 6) -> list[dict]:
        filters = StatsFilters()

        async def compute() -> list[dict]:
            entries = await self.stats_service.raw_history(user_id, filters)
            calculated = {
                "statistics": compute_statistics(entries),
                "setup": analyze_setups(entries),
                "mistakes": analyze_mistakes(entries),
                "strategyHealth": compute_strategy_health(entries),
            }
            return generate_coach_insights(entries, calculated)[:limit]

        return await coach_cache.get_or_set(("insights", user_id, limit), compute)

    async def playbook(self, user_id: int) -> dict:
        """Sprint 20 Phase 3 #6 -- "My Best Setups": per-POI-type win
        rate/R:R/best session/best day/example screenshots, ranked
        purely from this trader's own logged history (see
        app/engines/playbook_engine.py's docstring for what's
        deliberately NOT included yet -- average holding time has no
        underlying data to compute from)."""
        filters = StatsFilters()

        async def compute() -> dict:
            entries = await self.stats_service.raw_history(user_id, filters)
            return build_playbook(entries)

        return await coach_cache.get_or_set(("playbook", user_id), compute)

    async def deep_dive(self, user_id: int) -> dict:
        """Sprint 8 Phase 6 — ``GET /coach/deep-dive``. Same cached
        pattern as ``insights()``; reuses the exact same four engine
        calls (the fingerprint cache means calling both endpoints back
        to back doesn't recompute statistics/setups/mistakes/health
        twice)."""
        filters = StatsFilters()

        async def compute() -> dict:
            entries = await self.stats_service.raw_history(user_id, filters)
            statistics = compute_statistics(entries)
            setups = analyze_setups(entries)
            mistakes = analyze_mistakes(entries)
            health = compute_strategy_health(entries)
            return build_deep_dive(statistics, mistakes, setups, health)

        return await coach_cache.get_or_set(("deep_dive", user_id), compute)
