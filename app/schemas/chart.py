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


class TradeValidationResult(CamelModel):
    trade_status: str  # "VALID" | "INVALID"
    direction: str | None
    confidence: int
    reasons_passed: list[str] = Field(default_factory=list)
    reasons_failed: list[str] = Field(default_factory=list)
    suggested_entry: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_reward: float | None = None
    recommendation: str  # "TAKE" | "WAIT"


class ConfidenceBreakdown(CamelModel):
    trend_alignment: int
    poi_quality: int
    liquidity_quality: int
    bos_quality: int
    choch_quality: int
    fvg_quality: int
    rr_quality: int
    overall: int


class CoachExplanationResult(CamelModel):
    headline: str  # "BUY ANALYSIS" | "SELL ANALYSIS" | "NO TRADE"
    explanation: list[str] = Field(default_factory=list)
    confidence: ConfidenceBreakdown
    recommendation: str  # "BUY" | "SELL" | "WAIT"


class FullChartAnalysisResponse(CamelModel):
    """The combined Level 1 + 2 + 3 result — what the UI calls in one
    round trip for the common case."""

    analysis: ChartAnalysis
    validation: TradeValidationResult
    coach: CoachExplanationResult
    meta: ImageAnalyzeMeta | None = None


class FullCandlesAnalysisRequest(CamelModel):
    """Level 1 (candles) + Level 2 params in one request — the
    single-round-trip endpoint the UI calls for the common "I have
    price data" case."""

    candles: list[CandleIn] = Field(min_length=1)
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
