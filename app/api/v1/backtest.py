"""Sprint 13 — backtesting router.

``POST /api/v1/backtest/run`` — replays the existing SMC engine + Level
2 trade validator over historical OHLC data to see how the rules would
have performed. Stateless, no auth/DB dependency.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.schemas.backtest import BacktestRequest, BacktestResult
from app.services.backtest_service import BacktestService

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post(
    "/run",
    response_model=BacktestResult,
    summary="Sprint 13 — backtest the SMC rules against historical candle data",
)
async def run_backtest(body: BacktestRequest) -> BacktestResult:
    service = BacktestService()
    candles = [c.model_dump(by_alias=False) for c in body.candles]
    m15_candles = [c.model_dump(by_alias=False) for c in body.m15_candles] if body.m15_candles else None
    result = service.run(
        candles,
        m15_candles=m15_candles,
        lookback_window=body.lookback_window,
        lookback_window_m15=body.lookback_window_m15,
        min_rr=body.min_rr,
        direction=body.direction,
    )
    return BacktestResult(**result)
