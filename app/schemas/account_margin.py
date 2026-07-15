"""Account margin/floating-loss buffer schemas (Sprint 18).

Replaces a fixed stop loss with a passive early-warning system: the
MT5 EA pushes raw balance/equity/margin on every timer tick (same
cadence as the candle push), and this reports how close the account
is to XM Global's own margin call (50% margin level) and stop-out
(20% margin level) thresholds -- see
https://www.xm.com (Margin Call / Stop Out levels), confirmed via web
search on 2026-07-15. This is informational only; it never blocks or
closes anything, matching the user's own no-stop-loss strategy -- it
just makes the real risk visible instead of invisible.
"""
from __future__ import annotations

from datetime import datetime

from app.schemas.common import CamelModel

# XM Global's published thresholds for forex/CFD accounts on MT4/MT5.
# If the user is on a different broker/account type these can be
# overridden per-request via ``AccountMarginIngestRequest``.
DEFAULT_MARGIN_CALL_LEVEL_PCT = 50.0
DEFAULT_STOP_OUT_LEVEL_PCT = 20.0


class AccountMarginIngestRequest(CamelModel):
    balance: float
    equity: float
    margin: float
    margin_call_level_pct: float = DEFAULT_MARGIN_CALL_LEVEL_PCT
    stop_out_level_pct: float = DEFAULT_STOP_OUT_LEVEL_PCT


class AccountMarginOut(CamelModel):
    balance: float
    equity: float
    margin: float
    floating_pnl: float  # equity - balance
    margin_level_pct: float | None  # equity / margin * 100, None if margin == 0 (no open positions)
    margin_call_level_pct: float = DEFAULT_MARGIN_CALL_LEVEL_PCT
    stop_out_level_pct: float = DEFAULT_STOP_OUT_LEVEL_PCT
    buffer_to_margin_call_pct: float | None  # how far above the margin-call level, in margin-level points
    buffer_to_stop_out_pct: float | None  # how far above the stop-out level, in margin-level points
    status: str  # "NO_POSITIONS" | "SAFE" | "WARNING" | "DANGER"
    updated_at: datetime
