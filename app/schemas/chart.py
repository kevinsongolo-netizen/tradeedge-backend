"""Chart Analysis Engine schemas (Sprint 10).

``ChartAnalysis`` is the canonical Level-1 output shape — both Level-1
reading paths (deterministic candle math, best-effort vision AI) get
normalized into this one shape (see ``app.chart.normalize``) before
Level 2 (``TradeValidationResult``) and Level 3 (``CoachExplanation``)
ever see them. Those two never need to know which path produced their
input.
"""
from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel


class CandleIn(CamelModel):
    """One OHLC bar, as pasted/uploaded by the user (e.g. copied from
    MT5, TradingView's "Export chart data", or a CSV)."""

    time: str
    open: float
    high: float
    low: float
    close: float


class CandlesAnalyzeRequest(CamelModel):
    candles: list[CandleIn] = Field(min_length=1)


class ZoneOut(CamelModel):
    """A price zone (order block or FVG) worth showing in the UI."""

    kind: str  # "bullish" | "bearish"
    zone_type: str  # "Order Block" | "Fair Value Gap"
    high: float
    low: float
    mitigated: bool
    time: str | None = None


class ChartAnalysis(CamelModel):
    """Canonical Level-1 result — the same shape regardless of whether
    it came from real candle math or a vision AI's best-effort read of
    a screenshot."""

    source: str  # "candles" | "screenshot"
    trend: str  # "Bullish" | "Bearish" | "Ranging"
    structure: str
    current_price_context: str
    liquidity: str
    latest_event: str | None
    fvg_status: str | None
    premium_discount: str  # "Premium" | "Discount" | "Equilibrium"
    bias: str  # "BUY" | "SELL" | "NONE"
    confidence: int  # 0-100 — how confident THIS READ is, not trade quality
    zones: list[ZoneOut] = Field(default_factory=list)
    entry_zone: ZoneOut | None = None
    notes: list[str] = Field(default_factory=list)
    is_placeholder: bool = False


class ImageAnalyzeMeta(CamelModel):
    """Returned alongside an image-upload analysis so the UI can show
    "this is example data" banners honestly when running without a
    configured vision API key."""

    provider: str
    is_placeholder: bool


class ChartAnalysisResponse(CamelModel):
    analysis: ChartAnalysis
    meta: ImageAnalyzeMeta | None = None


class TradeValidationRequest(CamelModel):
    analysis: ChartAnalysis
    direction: str | None = None  # "buy" | "sell" — defaults to analysis.bias if omitted
    planned_rr: float | None = None
    has_m15_bos: bool = False
    has_m15_choch: bool = False
    has_m15_entry_confirmation: bool = False
    has_liquidity_sweep: bool = False
    min_rr: float = 2.0


class RuleCheck(CamelModel):
    """One step of the ONE official strategy's decision funnel (H4
    POI / M15 POI / POI Alignment / Entry & Target) -- lets the UI
    show exactly which rule passed, failed, or was never reached,
    instead of a single pass/fail flag."""

    rule: str
    status: str  # "PASSED" | "FAILED" | "NOT_CHECKED"
    detail: str


class TradeValidationResult(CamelModel):
    trade_status: str  # "VALID" | "INVALID"
    direction: str | None
    confidence: int
    reasons_passed: list[str] = Field(default_factory=list)
    reasons_failed: list[str] = Field(default_factory=list)
    rule_checks: list[RuleCheck] = Field(default_factory=list)
    suggested_entry: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_reward: float | None = None
    recommendation: str  # "TAKE" | "ADD" | "WAIT"

    # Sprint 18 -- Personal Averaging Strategy. These stay None/False
    # for any result produced by a strategy that doesn't use them (e.g.
    # the H4->M15 POI engine), so they're purely additive and don't
    # break existing callers or persisted rows.
    strategy: str | None = None
    daily_bias: str | None = None  # "BUY" | "SELL" | None
    add_on_signal: bool = False  # True when it's time to place the 2nd, same-size entry
    break_even_price: float | None = None  # price at which open entries net to ~0


class ConfidenceBreakdown(CamelModel):
    """Mirrors the ONE official strategy's own rule funnel (Sprint 18 --
    ``app.chart.personal_averaging_strategy``: Daily Bias / M15 POI /
    Entry Timing / Add-On Entry) -- each step is 100 if it passed, 0 if
    it failed or was never reached, so there is no second, independent
    quality score competing with the actual trade-validity decision.

    All fields default to 0 rather than being required: ``live_snapshots``
    rows persist this dict as raw JSON, so anything ingested before a
    field rename (the old h4Poi/m15Poi/poiAlignment/entryTarget shape,
    itself a replacement for an even older shape) would otherwise fail
    Pydantic validation on every later read of that row -- a 500 that
    only clears once the EA happens to push a fresh update for that
    exact symbol/timeframe. Defaulting means old or partial stored data
    degrades to 0s instead of ever crashing the read."""

    daily_bias: int = 0
    m15_poi: int = 0
    entry_timing: int = 0
    add_on: int = 0
    overall: int = 0


class CoachExplanationResult(CamelModel):
    headline: str  # "BUY ANALYSIS" | "SELL ANALYSIS" | "NO TRADE"
    explanation: list[str] = Field(default_factory=list)
    confidence: ConfidenceBreakdown
    recommendation: str  # "BUY" | "SELL" | "WAIT"


class MultiTimeframeConfirmation(CamelModel):
    """Sprint 12 — auto-derived M15 confirmation from real M15 candle
    data, in place of the manual has-m15-bos/choch/entry checkboxes."""

    aligned: bool
    has_m15_bos: bool
    has_m15_choch: bool
    has_m15_entry_confirmation: bool
    notes: list[str] = Field(default_factory=list)


class FullChartAnalysisResponse(CamelModel):
    """The combined Level 1 + 2 + 3 result — what the UI calls in one
    round trip for the common case."""

    analysis: ChartAnalysis
    validation: TradeValidationResult
    coach: CoachExplanationResult
    meta: ImageAnalyzeMeta | None = None
    multi_timeframe: MultiTimeframeConfirmation | None = None


class FullCandlesAnalysisRequest(CamelModel):
    """Level 1 (candles) + Level 2 params in one request — the
    single-round-trip endpoint the UI calls for the common "I have
    price data" case."""

    candles: list[CandleIn] = Field(min_length=1)
    m15_candles: list[CandleIn] | None = Field(
        default=None,
        description=(
            "Sprint 12 — optional M15 candles for automatic multi-timeframe "
            "confirmation. When supplied, has_m15_bos/has_m15_choch/"
            "has_m15_entry_confirmation are derived from real M15 structure "
            "and OR'd with the manual flags below rather than replacing them."
        ),
    )
    daily_candles: list[CandleIn] | None = Field(
        default=None,
        description=(
            "Sprint 18 — Personal Averaging Strategy's Daily Bias check "
            "(Step 1: bullish daily candle = BUY setups only, bearish = "
            "SELL only). Required for a VALID/TAKE result under the active "
            "strategy; omit only if you just want the Level-1 read/display."
        ),
    )
    open_trade_in_loss: bool = Field(
        default=False,
        description=(
            "Sprint 18 — set True when you already have a first position "
            "open on this pair and it's currently floating in a loss, so "
            "the strategy can check for rule 3's 2nd, same-size add-on "
            "entry instead of a fresh first entry."
        ),
    )
    direction: str | None = None
    planned_rr: float | None = None
    has_m15_bos: bool = False
    has_m15_choch: bool = False
    has_m15_entry_confirmation: bool = False
    has_liquidity_sweep: bool = False
    min_rr: float = 2.0


class CoachRequest(CamelModel):
    analysis: ChartAnalysis
    validation: TradeValidationResult
    min_rr: float = 2.0
