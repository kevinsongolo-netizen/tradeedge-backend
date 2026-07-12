"""Statistics / strategy-health / setup / mistake schemas
(``/api/v1/stats/*`` — Sections 4.5). Group breakdowns (byPair, byAsset,
...) use dynamic string keys, so they're typed as ``dict[str, GroupStats]``
rather than fixed fields, mirroring the JS engines' object shape.
"""
from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel


class GroupStats(CamelModel):
    """Core performance numbers for one slice of trades (one pair, one
    session, etc.) — the same shape ``statisticsCore`` returns per group."""

    total_trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: float
    loss_rate: float
    breakeven_rate: float
    total_pnl: float
    profit_factor: float
    expectancy: float
    average_win: float
    average_loss: float
    average_rr: float | None = Field(default=None, alias="averageRR")
    average_rule_score: float | None
    average_execution_score: float | None
    average_overall_score: float | None
    highest_score: float | None
    lowest_score: float | None
    trades_above90: int
    trades_below70: int
    largest_win: float
    largest_loss: float
    consecutive_wins: int
    consecutive_losses: int
    current_winning_streak: int
    current_losing_streak: int


class StatisticsResult(GroupStats):
    """Full statistics response — core numbers plus grouped breakdowns
    and AI-score-specific aggregates (Section 4.5's ``/stats/summary``)."""

    avg_score: int | None
    scored_count: int
    avg_winning_score: int | None
    avg_losing_score: int | None
    by_pair: dict[str, GroupStats] = Field(default_factory=dict)
    by_asset: dict[str, GroupStats] = Field(default_factory=dict)
    by_session: dict[str, GroupStats] = Field(default_factory=dict)
    by_day: dict[str, GroupStats] = Field(default_factory=dict)
    by_poi: dict[str, GroupStats] = Field(default_factory=dict)
    by_trend: dict[str, GroupStats] = Field(default_factory=dict)
    best_pair: str | None = None
    best_session: str | None = None
    best_setup: str | None = None
    worst_setup: str | None = None
    version: str


class ChartPoint(CamelModel):
    date: str | None = None
    value: float | None = None
    label: str | None = None


class GroupSeriesPoint(CamelModel):
    label: str
    value: float
    count: int


class ChartData(CamelModel):
    rule_score_trend: list[ChartPoint]
    execution_score_trend: list[ChartPoint]
    overall_score_trend: list[ChartPoint]
    win_rate_trend: list[ChartPoint]
    profit_factor_trend: list[ChartPoint]
    monthly_performance: list[GroupSeriesPoint]
    session_performance: list[GroupSeriesPoint]
    pair_performance: list[GroupSeriesPoint]


class HealthComponent(CamelModel):
    key: str
    label: str
    percentage: float | None
    score: float | None
    grade: str
    explanation: str


class StrategyHealthResult(CamelModel):
    health_score: float | None
    percentage: float | None
    grade: str | None
    verdict: str
    components: list[HealthComponent]
    version: str


class SetupGroupStat(CamelModel):
    key: str
    count: int
    wins: int
    losses: int
    breakeven: int
    total_pnl: float
    win_rate: float
    expectancy: float
    average_rr: float | None = Field(default=None, alias="averageRR")
    confident: bool
    rank_score: float


class SetupAnalysisResult(CamelModel):
    by_dimension: dict[str, list[SetupGroupStat]]
    top: dict[str, SetupGroupStat | None]
    best_setup: str | None
    sample_size: int


class HabitStat(CamelModel):
    name: str
    count: int
    pnl: float
    win_rate: float | None = None
    total_loss: float | None = None


class CategoryStat(CamelModel):
    count: int
    win_rate: float | None
    average_pnl: float


class MistakeAnalysisResult(CamelModel):
    most_common_mistake: HabitStat | None
    most_expensive_mistake: HabitStat | None
    most_common_rule_violation: HabitStat | None
    most_common_emotional_mistake: HabitStat | None
    most_profitable_habit: HabitStat | None
    most_harmful_habit: HabitStat | None
    lost_profit: dict[str, float]
    category_stats: dict[str, CategoryStat]
    top_mistakes: list[str]
    version: str
