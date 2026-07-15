"""Backtesting schemas (Sprint 13)."""
from __future__ import annotations

from pydantic import Field

from app.schemas.chart import CandleIn
from app.schemas.common import CamelModel


class BacktestRequest(CamelModel):
    """``candles`` is always the H4 series. ``m15Candles`` is now the
    normal path -- when supplied, this replays the active H4->M15 POI
    strategy (dual-timeframe, no forced R:R, no direction override).
    Omitting ``m15Candles`` falls back to the original single-timeframe
    Classic Bias replay (``min_rr``/``direction`` only apply there) --
    kept working for later reuse, not exposed in the current UI."""

    candles: list[CandleIn] = Field(min_length=1)
    m15_candles: list[CandleIn] | None = None
    lookback_window: int = 100
    lookback_window_m15: int = 100
    min_rr: float = 2.0
    direction: str | None = None


class BacktestTradeOut(CamelModel):
    entry_index: int
    entry_time: str
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    exit_time: str | None = None
    exit_price: float | None = None
    outcome: str  # "WIN" | "LOSS" | "OPEN"
    r_multiple: float | None = None


class BacktestResult(CamelModel):
    total_trades: int
    wins: int
    losses: int
    open_trades: int
    win_rate: float
    total_r_multiple: float
    average_r_multiple: float
    profit_factor: float | None = None
    trades: list[BacktestTradeOut] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
