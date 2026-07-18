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


class PlaybookSetup(CamelModel):
    """One row of "My Best Setups" (Sprint 20 Phase 3 #6) -- a POI type
    the trader has logged at least a few times, with its win rate, R:R,
    best session/day (each requiring their own minimum sample -- a
    single lucky trade in a session doesn't make it "best"), and up to
    two real winning-trade screenshots as examples. Deliberately no
    "average holding time" field -- see playbook_engine.py's docstring
    for why that isn't computable yet."""

    poi_type: str
    count: int
    wins: int
    losses: int
    breakeven: int
    win_rate: float
    average_rr: float | None = None
    expectancy: float
    best_session: str | None = None
    best_session_win_rate: float | None = None
    best_day: str | None = None
    best_day_win_rate: float | None = None
    example_screenshots: list[str] = Field(default_factory=list)


class PlaybookResponse(CamelModel):
    setups: list[PlaybookSetup] = Field(default_factory=list)
    sample_size: int


class EdgePattern(CamelModel):
    """One row of "Best Pattern" (Sprint 20 Phase 5) -- a full
    pair+direction+timeframe+POI-type+premium/discount-zone+session
    COMBINATION the trader has logged at least a few times, with its
    win rate/R:R/expectancy. See app/engines/edge_pattern_engine.py."""

    pair: str | None = None
    direction: str | None = None
    timeframe: str | None = None
    poi_type: str | None = None
    premium_discount: str | None = None
    session: str | None = None
    count: int
    wins: int
    losses: int
    breakeven: int
    win_rate: float
    average_rr: float | None = None
    expectancy: float


class MentorReportResponse(CamelModel):
    """Sprint 20 Phase 7 -- "AI Trade Mentor" periodic coaching report.
    See app/engines/mentor_report_engine.py's docstring. Every field
    below is None/empty whenever there wasn't enough data for THAT
    specific comparison -- never a fabricated stat."""

    period: str
    has_enough_data: bool = False
    period_sample_size: int = 0
    biggest_improvement: str | None = None
    biggest_repeated_mistake: str | None = None
    costliest_habit: str | None = None
    best_setup: str | None = None
    worst_setup: str | None = None
    best_pair: str | None = None
    pair_to_stop_trading: str | None = None
    winner_characteristic: str | None = None
    loser_characteristic: str | None = None


class EdgeCharacteristicRow(CamelModel):
    """Sprint 20 Phase 8 ("AI Learning Engine") -- one ranked
    characteristic (any kind: structural tag, session, zone, trend, ...)
    and what share of that side (winners or losers) actually has it.
    See app/engines/edge_profile_engine.py."""

    label: str
    share: float


class EdgeProfileResponse(CamelModel):
    """Sprint 20 Phase 8 -- comprehensive, whole-history characteristic
    discovery: "what made my winning trades different?" Not filtered to
    only the characteristics that separate winners from losers (see
    DiscoveredPatternsResponse for that narrower comparison) -- every
    characteristic that clears MIN_CHARACTERISTIC_SUPPORT on a side is
    ranked and shown, independently per side."""

    has_enough_data: bool = False
    winning_trade_count: int = 0
    losing_trade_count: int = 0
    winner_characteristics: list[EdgeCharacteristicRow] = Field(default_factory=list)
    loser_characteristics: list[EdgeCharacteristicRow] = Field(default_factory=list)


class DiscoveredPatternsResponse(CamelModel):
    """Sprint 20 Phase 6 -- "learn from my screenshots": standalone
    narrative statements about what separates this trader's own
    winning trades from their losing trades, discovered from their full
    history at once (no candidate setup needed). See
    app/engines/pattern_discovery_engine.py."""

    patterns: list[str] = Field(default_factory=list)
    winning_trade_count: int = 0
    losing_trade_count: int = 0
    has_enough_data: bool = False


class EdgePatternsResponse(CamelModel):
    patterns: list[EdgePattern] = Field(default_factory=list)
    # Sprint 20 Phase 6 -- "My Worst BTCUSD Sell": the same combination
    # ranking, read from the bottom instead of the top. See
    # app/engines/edge_pattern_engine.py's build_edge_patterns docstring.
    worst_patterns: list[EdgePattern] = Field(default_factory=list)
    sample_size: int
    has_enough_data: bool


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
    # Sprint 20 Phase 6 -- "Analyze Trade": for a losing trade, why it
    # likely didn't work out -- purely pattern-matched against the
    # trader's OWN similar losing/winning trades (characteristic_gap_
    # engine), never a fixed rule or a verdict on the setup itself.
    # Empty/None when the trade wasn't a loss, or there wasn't enough
    # similar history yet to say anything (same MIN_SAMPLE_FOR_GAP
    # honesty bar as the pre-trade insight).
    possible_reasons: list[str] = Field(default_factory=list)
    most_likely_cause: str | None = None
