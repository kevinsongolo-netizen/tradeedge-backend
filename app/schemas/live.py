"""Live MT5 feed schemas (Sprint 14 — Live MT5 Feed)."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.chart import (
    CandleIn,
    ChartAnalysis,
    CoachExplanationResult,
    MultiTimeframeConfirmation,
    TradeValidationResult,
)
from app.schemas.common import CamelModel


class LiveIngestRequest(CamelModel):
    """Body an MT5 EA (or any other live source) POSTs on every new
    bar. Mirrors ``FullCandlesAnalysisRequest`` plus a symbol/timeframe
    tag used as the storage key."""

    symbol: str
    timeframe: str
    candles: list[CandleIn] = Field(min_length=1)
    m15_candles: list[CandleIn] | None = None
    direction: str | None = None
    planned_rr: float | None = None
    has_m15_bos: bool = False
    has_m15_choch: bool = False
    has_m15_entry_confirmation: bool = False
    has_liquidity_sweep: bool = False
    min_rr: float = 2.0


class LiveSnapshotOut(CamelModel):
    symbol: str
    timeframe: str
    analysis: ChartAnalysis
    validation: TradeValidationResult
    coach: CoachExplanationResult
    multi_timeframe: MultiTimeframeConfirmation | None = None
    updated_at: datetime
