"""Backtesting service (Sprint 13). Stateless — same pattern as
``ChartService``."""
from __future__ import annotations

from typing import Any

from app.backtest.backtest_engine import run_backtest
from app.errors import ValidationError


class BacktestService:
    def run(self, candles: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        try:
            return run_backtest(candles, **kwargs)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
