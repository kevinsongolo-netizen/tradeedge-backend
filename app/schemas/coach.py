"""Coach schemas — ``GET /api/v1/coach/insights`` (Section 4.6) and,
since Sprint 8, ``GET /api/v1/coach/deep-dive`` (Vision Phase 6)."""
from __future__ import annotations

from app.schemas.common import CamelModel


class CoachInsight(CamelModel):
    level: str  # "positive" | "warning" | "info" | "critical"
    text: str
    icon: str | None = None


class CoachInsightsResponse(CamelModel):
    insights: list[CoachInsight]


class DimensionStat(CamelModel):
    """One ranked row from ``setup_engine.group_stats()`` — a pair,
    session, day, POI, or confirmation-combo with its win rate,
    expectancy, and sample size."""

    key: str
    count: int
    wins: int
    losses: int
    breakeven: int
    win_rate: float
    expectancy: float
    total_pnl: float
    average_rr: float | None = None
    confident: bool


class MistakeSummary(CamelModel):
    name: str
    count: int
    pnl: float
    total_loss: float


class CoachDeepDive(CamelModel):
    """Sprint 8 Phase 6 — structured answers to the vision doc's
    specific coaching questions, built from Sprint 6's existing
    statistics/mistake/setup/strategy-health engines."""

    why_losing: str
    why_winning: str
    biggest_mistake: MistakeSummary | None = None
    best_setup: DimensionStat | None = None
    worst_setup: DimensionStat | None = None
    worst_day_to_trade: DimensionStat | None = None
    best_session: DimensionStat | None = None
    pair_to_stop_trading: DimensionStat | None = None
    sample_size: int
    version: str
