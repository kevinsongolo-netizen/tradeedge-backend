"""Coach schemas — ``GET /api/v1/coach/insights`` (Section 4.6) and,
since Sprint 8, ``GET /api/v1/coach/deep-dive`` (Vision Phase 6)."""
from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.trade import TradeBase


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


class TradeReviewRequest(TradeBase):
    """Request body for ``POST /coach/review-trade`` (Sprint 11 — AI
    review-after-close). Accepts the same fields as the journal (pair,
    direction, entry, exit, sl, tp, rr, h4Trend, h4PoiType, rulesFollowed,
    workedTags, failedTags, exitReason, notes, ...). Works on any closed
    trade whether or not it's been synced to the backend yet — the whole
    trade is supplied in the request body."""


class TradeReviewResult(CamelModel):
    outcome: str  # "WIN" | "LOSS" | "BREAKEVEN" | "UNKNOWN"
    headline: str
    what_worked: list[str] = Field(default_factory=list)
    what_went_wrong: list[str] = Field(default_factory=list)
    lesson: str
    followed_plan_note: str
    # Sprint 20 Phase 2 #4 -- planned-vs-actual, compared against the
    # trader's OWN similar closed trades (trade_lesson_engine.py), not
    # a fixed rule. has_history=False means there weren't enough
    # similar past trades yet to draw a comparison (said plainly in
    # `lessons` rather than guessing).
    has_enough_history: bool = True
    similar_sample_size: int = 0
    similar_wins: int = 0
    similar_losses: int = 0
    lessons: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
