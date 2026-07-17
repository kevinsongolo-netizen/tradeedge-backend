"""Live MT5 feed schemas (Sprint 14; simplified Sprint 20).

Sprint 20 -- the ingest payload dropped every field that only existed
to feed the retired rule engine (candles, m15/daily candles, BOS/CHOCH
flags, planned R:R, ...). An EA now only needs to say "here is the
current price for this symbol/timeframe."
"""
from __future__ import annotations

from datetime import datetime

from app.schemas.common import CamelModel


class LiveIngestRequest(CamelModel):
    """Body an MT5 EA (or any other live source) POSTs whenever it has
    a fresh price for a symbol/timeframe."""

    symbol: str
    timeframe: str
    price: float | None = None
    bid: float | None = None
    ask: float | None = None


class LiveSnapshotOut(CamelModel):
    symbol: str
    timeframe: str
    price: float | None = None
    bid: float | None = None
    ask: float | None = None
    updated_at: datetime


class OpenTradeAlert(CamelModel):
    """Sprint 20 -- the repurposed Scanner's output: where live price
    sits relative to an already-logged open trade's own SL/TP. Never a
    verdict on whether the trade itself was a good idea."""

    trade_id: str | None = None
    pair: str | None = None
    direction: str | None = None
    entry: float | None = None
    sl: float | None = None
    tp: float | None = None
    current_price: float | None = None
    status: str  # "SL_HIT" | "TP_HIT" | "NEAR_SL" | "NEAR_TP" | "MONITORING"
    needs_attention: bool
    message: str


class OpenTradeAlertsResponse(CamelModel):
    alerts: list[OpenTradeAlert]
