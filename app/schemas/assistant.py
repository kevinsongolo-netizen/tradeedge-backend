"""Pre-Trade Check schemas.

v2 — rebuilt per the user's explicit instruction that every feature
must run the ONE official H4->M15 POI strategy, not a separate manual
checklist. ``POST /api/v1/assistant/pretrade-analysis`` now takes H4 +
M15 candles (same shape as Chart Analysis Engine / Backtest) instead
of manually-ticked BOS/CHOCH/trend/direction fields. The strategy's own
VALID/WAIT decision is always the final word; everything from
``tradeQualityScore`` down is supplementary ML/historical context that
can never override it (per the user's explicit rule #5).
"""
from __future__ import annotations

from pydantic import Field

from app.schemas.chart import CandleIn, RuleCheck
from app.schemas.common import CamelModel


class PreTradeAnalysisRequest(CamelModel):
    pair: str
    asset: str | None = None
    session: str | None = None
    h4_candles: list[CandleIn] = Field(min_length=1)
    m15_candles: list[CandleIn] = Field(min_length=1)


class PreTradeAnalysisResult(CamelModel):
    # --- the ONE official strategy's own decision -- never overridden ---
    trade_status: str  # "VALID" | "INVALID"
    direction: str | None
    rule_checks: list[RuleCheck] = Field(default_factory=list)
    reasons_passed: list[str] = Field(default_factory=list)
    reasons_failed: list[str] = Field(default_factory=list)
    suggested_entry: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_reward: float | None = None
    recommendation: str  # "TAKE" | "WAIT" -- the strategy's own call

    # --- supplementary ML/historical context only, shown separately ---
    trade_quality_score: float | None = None
    win_probability: float | None = None
    ai_confidence: str = "Low"  # "High" | "Medium" | "Low"
    risk_level: str = "Medium"  # "Low" | "Medium" | "High"
    expected_rr: float | None = None
    historical_win_rate: float | None = None
    similar_trades_count: int = 0
    ml_recommendation: str | None = None  # "Strong Buy" | "Buy" | "Wait" | "Avoid" -- informational only
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    historical_reasons: list[str] = Field(default_factory=list)
    ml_available: bool = False
    model_version: str | None = None
    algorithm: str | None = None
