"""Multi-timeframe confirmation (Chart Analysis Engine — Sprint 12).

Automatically derives the M15 confirmation flags Level 2 trade
validation already accepts (``has_m15_bos``, ``has_m15_choch``,
``has_m15_entry_confirmation`` — see ``app/chart/trade_validator.py``)
from a *real* M15 ``ChartAnalysis`` instead of requiring the user to
self-report them via checkboxes. Purely additive: manual checkboxes
remain a valid fallback whenever M15 candle data isn't supplied, and
the two are OR'd together by the caller (``ChartService``), never
replaced.
"""
from __future__ import annotations

from typing import Any

from app.schemas.chart import ChartAnalysis


def confirm_with_m15(m15_analysis: ChartAnalysis, direction: str) -> dict[str, Any]:
    """``direction``: the resolved trade direction ("buy"/"sell") —
    the H4 bias, or the user's override."""
    wanted = "bullish" if direction == "buy" else "bearish"
    trend_wanted = "Bullish" if direction == "buy" else "Bearish"

    latest = (m15_analysis.latest_event or "").lower()
    has_bos = "bos" in latest and wanted in latest
    has_choch = "choch" in latest and wanted in latest
    entry_confirmation = m15_analysis.trend == trend_wanted

    notes: list[str] = []
    if has_bos:
        notes.append(f"M15 shows a {wanted} BOS, confirming the H4 {direction} bias.")
    if has_choch:
        notes.append(f"M15 shows a {wanted} CHOCH, an early confirmation of the H4 {direction} bias.")
    if entry_confirmation:
        notes.append(f"M15 trend ({m15_analysis.trend}) agrees with the H4 bias.")
    if not (has_bos or has_choch or entry_confirmation):
        notes.append("M15 does not yet confirm the H4 bias — no matching BOS/CHOCH or trend alignment found.")

    return {
        "aligned": has_bos or has_choch or entry_confirmation,
        "has_m15_bos": has_bos,
        "has_m15_choch": has_choch,
        "has_m15_entry_confirmation": entry_confirmation,
        "notes": notes,
    }
