"""Backtesting service (Sprint 13, extended for the H4->M15 dual-
timeframe strategy). Stateless -- same pattern as ``ChartService``."""
from __future__ import annotations

from typing import Any

from app.backtest.backtest_engine import run_backtest
from app.backtest.h4_m15_backtest_engine import run_backtest_h4_m15
from app.errors import ValidationError


class BacktestService:
    def run(
        self,
        candles: list[dict[str, Any]],
        *,
        m15_candles: list[dict[str, Any]] | None = None,
        lookback_window: int = 100,
        lookback_window_m15: int = 100,
        min_rr: float = 2.0,
        direction: str | None = None,
    ) -> dict[str, Any]:
        try:
            if m15_candles:
                # Active strategy: dual-timeframe H4->M15 POI replay.
                return run_backtest_h4_m15(
                    candles,
                    m15_candles,
                    lookback_window_h4=lookback_window,
                    lookback_window_m15=lookback_window_m15,
                )
            # No M15 candles supplied -- fall back to the original
            # single-timeframe Classic Bias replay (kept for later
            # reuse, not the path the current UI exercises).
            return run_backtest(candles, lookback_window=lookback_window, min_rr=min_rr, direction=direction)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
