"""Trade validation against SMC trading rules (Chart Analysis Engine —
Level 2).

Pure function of a ``ChartAnalysis`` (already normalized from either
Level-1 reading path — see ``app.chart.normalize``) plus a handful of
lower-timeframe confirmation flags and the user's planned R:R. Knows
nothing about HTTP or image/candle parsing — same convention as every
other engine in this app (see ``app/engines/rule_engine.py`` etc.).

Rules encoded here (from the Chart Analysis Engine spec):

* H4 trend: only trade in the direction of the identified trend.
* Point of Interest: price must be inside/reacting from a valid POI
  (order block, FVG, breaker, demand/supply — represented generically
  here as ``analysis.entry_zone`` or a descriptive "inside ..." read).
* Lower-timeframe confirmation: BOS, CHOCH, or an explicit entry
  confirmation flag.
* Minimum Risk:Reward = 1:2 — trades below this are rejected outright.
"""
from __future__ import annotations

from app.schemas.chart import ChartAnalysis, ZoneOut

DEFAULT_MIN_RR = 2.0
ENTRY_ZONE_BUFFER_PCT = 0.25  # stop-loss sits this fraction of the zone's height beyond its far edge


def _direction_from_bias(bias: str) -> str | None:
    if bias == "BUY":
        return "buy"
    if bias == "SELL":
        return "sell"
    return None


def _trend_matches(direction: str, trend: str) -> bool:
    return (direction == "buy" and trend == "Bullish") or (direction == "sell" and trend == "Bearish")


def _poi_ok(analysis: ChartAnalysis, direction: str) -> bool:
    if analysis.entry_zone is not None:
        return analysis.entry_zone.kind == ("bullish" if direction == "buy" else "bearish")
    context = (analysis.current_price_context or "").lower()
    wanted = "bullish" if direction == "buy" else "bearish"
    return "inside" in context and wanted in context


def _suggest_entry_sl_tp(
    entry_zone: ZoneOut, direction: str, min_rr: float
) -> tuple[float, float, float, float]:
    """Deterministic, only ever called for candle-sourced analyses
    (screenshot reads don't have exact numeric zones). Entry at the
    zone's midpoint; stop beyond the far edge by a buffer proportional
    to the zone's own height; target at exactly ``min_rr`` — a
    conservative, always-reproducible suggestion, not a promise."""
    zone_height = max(entry_zone.high - entry_zone.low, 1e-9)
    entry = (entry_zone.high + entry_zone.low) / 2
    buffer = zone_height * ENTRY_ZONE_BUFFER_PCT
    if direction == "buy":
        stop_loss = entry_zone.low - buffer
        risk = entry - stop_loss
        take_profit = entry + risk * min_rr
    else:
        stop_loss = entry_zone.high + buffer
        risk = stop_loss - entry
        take_profit = entry - risk * min_rr
    rr = min_rr  # suggestion is constructed to hit exactly this ratio
    return entry, stop_loss, take_profit, rr


def validate_trade(
    analysis: ChartAnalysis,
    *,
    direction: str | None = None,
    planned_rr: float | None = None,
    has_m15_bos: bool = False,
    has_m15_choch: bool = False,
    has_m15_entry_confirmation: bool = False,
    has_liquidity_sweep: bool = False,
    min_rr: float = DEFAULT_MIN_RR,
) -> dict:
    resolved_direction = direction or _direction_from_bias(analysis.bias)

    if resolved_direction is None:
        return {
            "tradeStatus": "INVALID",
            "direction": None,
            "confidence": 0,
            "reasonsPassed": [],
            "reasonsFailed": ["✗ No clear directional bias could be determined from the analysis"],
            "suggestedEntry": None,
            "stopLoss": None,
            "takeProfit": None,
            "riskReward": None,
            "recommendation": "WAIT",
        }

    passed: list[str] = []
    failed: list[str] = []
    trend_label = "Bullish" if resolved_direction == "buy" else "Bearish"

    if _trend_matches(resolved_direction, analysis.trend):
        passed.append(f"✓ H4 {trend_label} Trend")
    else:
        failed.append("✗ Against Higher Time Frame Trend")

    if _poi_ok(analysis, resolved_direction):
        passed.append(f"✓ Price inside a valid {trend_label} Point of Interest")
    else:
        failed.append("✗ Price is not at a valid Point of Interest")

    m15_confirmed = has_m15_bos or has_m15_choch or has_m15_entry_confirmation or bool(analysis.latest_event)
    if m15_confirmed:
        label = analysis.latest_event or "Entry confirmation present"
        passed.append(f"✓ {label}")
    else:
        failed.append("✗ No Confirmation")

    if has_liquidity_sweep:
        passed.append("✓ Liquidity swept")

    suggested_entry = suggested_sl = suggested_tp = suggested_rr = None
    if analysis.source == "candles" and analysis.entry_zone is not None:
        suggested_entry, suggested_sl, suggested_tp, suggested_rr = _suggest_entry_sl_tp(
            analysis.entry_zone, resolved_direction, min_rr
        )

    effective_rr = planned_rr if planned_rr is not None else suggested_rr
    if effective_rr is not None:
        if effective_rr >= min_rr:
            passed.append(f"✓ RR = 1:{effective_rr:.1f}")
        else:
            failed.append(f"✗ RR below 1:{min_rr:.0f}")
    else:
        failed.append("✗ Risk:Reward could not be determined — provide a planned R:R")

    trade_status = "VALID" if not failed else "INVALID"
    total_checks = len(passed) + len(failed)
    confidence = round((len(passed) / total_checks) * 100) if total_checks else 0

    return {
        "tradeStatus": trade_status,
        "direction": resolved_direction,
        "confidence": confidence,
        "reasonsPassed": passed,
        "reasonsFailed": failed,
        "suggestedEntry": suggested_entry,
        "stopLoss": suggested_sl,
        "takeProfit": suggested_tp,
        "riskReward": effective_rr if trade_status == "VALID" else effective_rr,
        "recommendation": "TAKE" if trade_status == "VALID" else "WAIT",
    }
