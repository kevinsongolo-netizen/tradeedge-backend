"""Backtesting schemas (Sprint 13)."""
from __future__ import annotations

from pydantic import Field

from app.schemas.chart import CandleIn
from app.schemas.common import CamelModel


class BacktestRequest(CamelModel):
    """``candles`` is always the H4 series (kept for the retired dual-
    timeframe fallback below). Supplying ``dailyCandles`` (Sprint 18)
    alongside ``m15Candles`` is now the normal path -- it replays the
    active Personal Averaging Strategy (Daily Bias + M15 POI, no fixed
    SL/TP). Supplying only ``m15Candles`` (no ``dailyCandles``) falls
    back to the retired H4->M15 POI dual-timeframe replay -- kept
    working for later reuse, not exposed in the current UI. Omitting
    both falls back further, to the original single-timeframe Classic
    Bias replay (``min_rr``/``direction`` only apply there)."""

    candles: list[CandleIn] = Field(min_length=1)
    m15_candles: list[CandleIn] | None = None
    daily_candles: list[CandleIn] | None = None
    lookback_window: int = 100
    lookback_window_m15: int = 100
    lookback_window_daily: int = 30
    target_net_profit_per_unit: float = 0.0
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


class BacktestCycleEntryOut(CamelModel):
    price: float
    time: str


class BacktestCycleOut(CamelModel):
    """Sprint 18 -- one Personal Averaging Strategy cycle (a first
    entry, plus an optional same-size add-on), replacing the fixed
    SL/TP-based ``BacktestTradeOut`` shape for this strategy."""

    direction: str
    entries: list[BacktestCycleEntryOut] = Field(default_factory=list)
    add_on_used: bool = False
    exit_time: str | None = None
    exit_price: float | None = None
    net_pnl_per_unit: float
    max_adverse_excursion: float
    bars_held: int
    outcome: str  # "CLOSED" | "OPEN"


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

    # Sprint 18 -- populated only by the Personal Averaging Strategy
    # replay (see personal_averaging_backtest_engine.py's module
    # docstring for why win_rate/r_multiple aren't meaningful risk
    # measures for a no-stop-loss averaging strategy). None/empty for
    # the retired H4->M15 and Classic Bias replays.
    strategy: str | None = None
    cycles_total: int | None = None
    cycles_closed: int | None = None
    cycles_open: int | None = None
    add_on_rate_pct: float | None = None
    avg_bars_held: float | None = None
    max_adverse_excursion: float | None = None
    cycles_detail: list[BacktestCycleOut] = Field(default_factory=list)
