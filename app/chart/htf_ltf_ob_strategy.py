"""H4 -> M15 Order Block strategy (custom user-defined strategy,
added after the "Classic Bias" strategy -- see the note at the top of
``app/chart/trade_validator.py`` for that one, kept fully intact and
just not wired in as the active strategy anymore).

Exact rules as specified by the user:

1. On the H4 timeframe, wait for price to touch an untested order
   block (a candle range overlapping the OB's zone for the first
   time). Touching a BEARISH H4 OB sets up a candidate SELL; touching
   a BULLISH H4 OB sets up a candidate BUY.
2. Once that H4 touch has happened, drop to M15 and wait for price to
   ALSO touch a matching-direction order block there (a bearish OB
   for a sell, a bullish OB for a buy). This M15 touch is the actual
   entry trigger -- the H4 touch alone is not enough.
3. Entry = the M15 order block's midpoint.
4. Stop loss = just beyond the M15 order block's far edge -- above
   the top of a bearish OB for a sell, below the bottom of a bullish
   OB for a buy (a small buffer added for slippage, same convention
   ``trade_validator._suggest_entry_sl_tp`` already used).
5. Take profit = the near edge of the next OPPOSITE, still-unmitigated
   order block on H4 (the "target zone"): the TOP of a bullish OB for
   a sell (price is descending into it from above), or the BOTTOM of
   a bearish OB for a buy (price is ascending into it from below).

Unlike the Classic Bias strategy, this one does not gate on H4 trend
direction or a minimum R:R -- the user's rules don't mention either,
so R:R is reported for reference but never used to reject a setup.
"""
from __future__ import annotations

from app.chart.candle_smc_engine import OrderBlock, SmcAnalysis

STRATEGY_NAME = "H4->M15 OB Strategy"

# Fraction of the M15 order block's own height, added beyond its far
# edge as stop-loss buffer room (mirrors the classic strategy's
# ENTRY_ZONE_BUFFER_PCT convention in trade_validator.py).
SL_BUFFER_PCT = 0.15


def _invalid(direction: str | None, confidence: int, passed: list[str], failed: list[str]) -> dict:
    return {
        "tradeStatus": "INVALID",
        "direction": direction,
        "confidence": confidence,
        "reasonsPassed": passed,
        "reasonsFailed": failed,
        "suggestedEntry": None,
        "stopLoss": None,
        "takeProfit": None,
        "riskReward": None,
        "recommendation": "WAIT",
    }


def _nearest_opposite_ob(h4: SmcAnalysis, direction: str) -> OrderBlock | None:
    """The target zone: nearest unmitigated H4 OB opposite our
    direction (a bullish target below price for a sell, a bearish
    target above price for a buy)."""
    return h4.nearest_unmitigated_ob_bullish if direction == "sell" else h4.nearest_unmitigated_ob_bearish


def validate_h4_m15_ob(h4: SmcAnalysis, m15: SmcAnalysis | None) -> dict:
    """Pure function -- no I/O, matches the same output shape as
    ``app.chart.trade_validator.validate_trade`` so it's a drop-in
    replacement wherever that was called (see ``ChartService.
    full_analysis_from_candles``)."""
    passed: list[str] = []
    failed: list[str] = []

    h4_touch = h4.price_in_order_block
    if h4_touch is None:
        failed.append("✗ Price has not touched an untested H4 order block yet")
        return _invalid(None, 0, passed, failed)

    direction = "sell" if h4_touch.kind == "bearish" else "buy"
    trend_label = "Bearish" if direction == "sell" else "Bullish"
    passed.append(f"✓ Price touched an H4 {trend_label} Order Block ({h4_touch.low:.5f}-{h4_touch.high:.5f})")

    if m15 is None:
        failed.append("✗ No M15 candle data supplied -- can't check for the M15 entry trigger")
        return _invalid(direction, 33, passed, failed)

    wanted_kind = "bearish" if direction == "sell" else "bullish"
    m15_touch = m15.price_in_order_block
    if m15_touch is None or m15_touch.kind != wanted_kind:
        failed.append(f"✗ Waiting for price to touch a matching {wanted_kind.capitalize()} Order Block on M15")
        return _invalid(direction, 33, passed, failed)

    passed.append(
        f"✓ Price touched a matching M15 {wanted_kind.capitalize()} Order Block "
        f"({m15_touch.low:.5f}-{m15_touch.high:.5f})"
    )

    entry = (m15_touch.high + m15_touch.low) / 2
    m15_height = max(m15_touch.high - m15_touch.low, 1e-9)
    buffer = m15_height * SL_BUFFER_PCT
    if direction == "sell":
        stop_loss = m15_touch.high + buffer
    else:
        stop_loss = m15_touch.low - buffer

    target_ob = _nearest_opposite_ob(h4, direction)
    target_label = "Bullish" if direction == "sell" else "Bearish"
    # Guard against a target that isn't actually on the correct side
    # of entry yet (e.g. not enough H4 history) -- rather than report
    # a nonsensical negative R:R, treat it as no target found.
    if target_ob is not None:
        take_profit_candidate = target_ob.high if direction == "sell" else target_ob.low
        wrong_side = (direction == "sell" and take_profit_candidate >= entry) or (
            direction == "buy" and take_profit_candidate <= entry
        )
        if wrong_side:
            target_ob = None

    if target_ob is None:
        failed.append(f"✗ No opposite unmitigated H4 {target_label} Order Block found yet to use as a target")
        return _invalid(direction, 67, passed, failed)

    take_profit = target_ob.high if direction == "sell" else target_ob.low
    passed.append(f"✓ Opposite H4 {target_label} Order Block found as target ({target_ob.low:.5f}-{target_ob.high:.5f})")

    if direction == "sell":
        risk = stop_loss - entry
        reward = entry - take_profit
    else:
        risk = entry - stop_loss
        reward = take_profit - entry
    risk_reward = round(reward / risk, 2) if risk > 0 else None

    return {
        "tradeStatus": "VALID",
        "direction": direction,
        "confidence": 100,
        "reasonsPassed": passed,
        "reasonsFailed": failed,
        "suggestedEntry": entry,
        "stopLoss": stop_loss,
        "takeProfit": take_profit,
        "riskReward": risk_reward,
        "recommendation": "TAKE",
    }
