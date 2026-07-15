"""H4 -> M15 Point-of-Interest strategy (custom user-defined strategy,
v3 -- adds a structured, step-by-step rule checklist so every caller
can show exactly which rule passed/failed/was never reached, per the
user's explicit request; no change to the underlying decision logic
from v2). The "Classic Bias" strategy (trend + premium/discount +
BOS/CHOCH) is kept fully intact and untouched in
``app/chart/trade_validator.py`` for later reuse if ever needed.

Official rules, exactly as specified by the user:

Step 1 -- H4 Point of Interest (POI). The FIRST thing checked is NOT
trend. Check whether price has touched or reacted from a valid H4 POI
-- a Bullish Order Block, Bearish Order Block, Bullish Fair Value Gap,
or Bearish Fair Value Gap. If price hasn't touched/reacted from any
H4 OB or FVG: return WAIT, do not continue to M15 at all.

Step 2 -- M15 Point of Interest. If the H4 POI is valid, switch to
M15 and check the same thing there (OB or FVG, bullish or bearish).
If price hasn't touched/reacted from a valid M15 OB or FVG: WAIT.

Step 3 -- POI alignment. The H4 POI and the M15 POI must be the same
kind (H4 bullish + M15 bullish = BUY, H4 bearish + M15 bearish =
SELL). If they don't align: WAIT. (Deliberately called "POI
alignment", not "direction"/"trend" -- this strategy is not
trend-first; alignment is about the two zones matching, nothing else.)

Step 4 -- Entry & target. Only VALID/TAKE when H4 POI touched, M15 POI
touched, the two align, AND a valid opposite M15 target zone exists.
Stop loss sits beyond the M15 POI (the same zone used for entry). Take
profit sits at the NEXT M15 Order Block or M15 Fair Value Gap (opposite
kind) -- NOT an H4 zone; the target lives on the same M15 timeframe as
the entry. No fixed R:R is forced; entry/SL/TP fall out of real market
structure only.

Explicitly NOT required to determine VALID/WAIT (per the user's
instruction): H4 trend, BOS confirmation, CHOCH confirmation, liquidity
sweep, or any "entry confirmation" flag. Those may still be shown
elsewhere as descriptive context, but none of them gate this strategy's
decision -- this module is the ONE place that decision is made; every
caller (Chart Analysis Engine, Live Feed, Scanner, Backtest, Pre-Trade
Check) calls this same function, never a copy of this logic.

``rule_checks`` (new in v3) breaks the decision down into the exact
steps above so any caller can render a plain checklist (rule name,
status PASSED/FAILED/NOT_CHECKED, one-line detail) instead of parsing
free-text reasons -- ``reasons_passed``/``reasons_failed`` are kept
too, unchanged, for backwards compatibility with anything already
reading them.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.chart.candle_smc_engine import FairValueGap, OrderBlock, SmcAnalysis

STRATEGY_NAME = "H4->M15 POI Strategy (Order Block or Fair Value Gap)"

# Fraction of the M15 POI zone's own height, added beyond its far edge
# as stop-loss buffer room (mirrors the Classic Bias strategy's own
# ENTRY_ZONE_BUFFER_PCT convention in trade_validator.py).
SL_BUFFER_PCT = 0.15

PASSED = "PASSED"
FAILED = "FAILED"
NOT_CHECKED = "NOT_CHECKED"

RULE_H4_POI = "H4 Order Block/FVG"
RULE_M15_POI = "M15 Order Block/FVG"
RULE_POI_ALIGNMENT = "POI Alignment"
RULE_ENTRY_TARGET = "Entry / SL / TP"

_NOT_CHECKED_DETAIL = "Not checked -- an earlier rule must pass first"


@dataclass
class Poi:
    """A touched Point of Interest -- either an Order Block or a Fair
    Value Gap, normalized to the same (kind, low, high) shape so the
    rest of this module doesn't need to care which one it is."""

    kind: str  # "bullish" | "bearish"
    zone_type: str  # "Order Block" | "Fair Value Gap"
    low: float
    high: float


def _poi_from_ob(ob: OrderBlock) -> Poi:
    return Poi(kind=ob.kind, zone_type="Order Block", low=ob.low, high=ob.high)


def _poi_from_fvg(fvg: FairValueGap) -> Poi:
    return Poi(kind=fvg.kind, zone_type="Fair Value Gap", low=fvg.bottom, high=fvg.top)


def _touched_poi(smc: SmcAnalysis) -> Poi | None:
    """The most recent UNTESTED zone (Order Block or Fair Value Gap)
    that current price is sitting inside right now -- "touched or
    reacted from", per the spec. Checks Order Blocks first, then Fair
    Value Gaps, both walked newest-to-oldest so the freshest touch
    wins if more than one zone happens to overlap price at once."""
    current = smc.current_price
    for ob in reversed(smc.order_blocks):
        if not ob.mitigated and ob.low <= current <= ob.high:
            return _poi_from_ob(ob)
    for gap in reversed(smc.fair_value_gaps):
        if not gap.mitigated and gap.bottom <= current <= gap.top:
            return _poi_from_fvg(gap)
    return None


def _nearest_opposite_poi(m15: SmcAnalysis, direction: str) -> Poi | None:
    """The M15 target zone: nearest unmitigated OB or FVG opposite our
    direction (a bullish target below price for a sell, a bearish
    target above price for a buy) -- whichever of the two is closer to
    entry is "the next" one, per the spec's "next M15 OB or FVG"."""
    wanted = "bullish" if direction == "sell" else "bearish"
    candidates: list[Poi] = []
    ob = m15.nearest_unmitigated_ob_bullish if wanted == "bullish" else m15.nearest_unmitigated_ob_bearish
    if ob is not None:
        candidates.append(_poi_from_ob(ob))
    fvg = m15.nearest_unmitigated_fvg_bullish if wanted == "bullish" else m15.nearest_unmitigated_fvg_bearish
    if fvg is not None:
        candidates.append(_poi_from_fvg(fvg))
    if not candidates:
        return None
    # "Near edge" = the boundary price reaches first travelling toward
    # the zone (top of a bullish target approached from above for a
    # sell; bottom of a bearish target approached from below for a
    # buy) -- whichever candidate's near edge is closest to entry is
    # genuinely "the next" one structurally.
    def near_edge(poi: Poi) -> float:
        return poi.high if direction == "sell" else poi.low

    entry_ref = m15.current_price
    candidates.sort(key=lambda p: abs(near_edge(p) - entry_ref))
    return candidates[0]


def _checklist(
    h4_status: str,
    h4_detail: str,
    m15_status: str = NOT_CHECKED,
    m15_detail: str = _NOT_CHECKED_DETAIL,
    align_status: str = NOT_CHECKED,
    align_detail: str = _NOT_CHECKED_DETAIL,
    entry_status: str = NOT_CHECKED,
    entry_detail: str = _NOT_CHECKED_DETAIL,
) -> list[dict]:
    return [
        {"rule": RULE_H4_POI, "status": h4_status, "detail": h4_detail},
        {"rule": RULE_M15_POI, "status": m15_status, "detail": m15_detail},
        {"rule": RULE_POI_ALIGNMENT, "status": align_status, "detail": align_detail},
        {"rule": RULE_ENTRY_TARGET, "status": entry_status, "detail": entry_detail},
    ]


def _invalid(
    direction: str | None, confidence: int, passed: list[str], failed: list[str], rule_checks: list[dict]
) -> dict:
    return {
        "tradeStatus": "INVALID",
        "direction": direction,
        "confidence": confidence,
        "reasonsPassed": passed,
        "reasonsFailed": failed,
        "ruleChecks": rule_checks,
        "suggestedEntry": None,
        "stopLoss": None,
        "takeProfit": None,
        "riskReward": None,
        "recommendation": "WAIT",
    }


def validate_h4_m15_ob(h4: SmcAnalysis, m15: SmcAnalysis | None) -> dict:
    """Pure function -- no I/O. Same output shape as
    ``app.chart.trade_validator.validate_trade`` (drop-in replacement
    wherever that was called -- see ``ChartService.
    full_analysis_from_candles``), plus a new ``ruleChecks`` field (see
    module docstring)."""
    passed: list[str] = []
    failed: list[str] = []

    # Step 1 -- H4 POI (Order Block OR Fair Value Gap).
    h4_poi = _touched_poi(h4)
    if h4_poi is None:
        detail = "Price has not touched or reacted from a valid H4 Order Block or Fair Value Gap"
        failed.append(f"✗ {detail}")
        return _invalid(None, 0, passed, failed, _checklist(FAILED, detail))

    direction = "sell" if h4_poi.kind == "bearish" else "buy"
    poi_label = "Bearish" if direction == "sell" else "Bullish"
    h4_detail = f"Price touched an H4 {poi_label} {h4_poi.zone_type} ({h4_poi.low:.5f}-{h4_poi.high:.5f})"
    passed.append(f"✓ {h4_detail}")

    # Step 2 -- M15 POI (Order Block OR Fair Value Gap).
    if m15 is None:
        detail = "No M15 candle data supplied -- can't check for the M15 Point of Interest"
        failed.append(f"✗ {detail}")
        return _invalid(direction, 25, passed, failed, _checklist(PASSED, h4_detail, FAILED, detail))

    m15_poi = _touched_poi(m15)
    if m15_poi is None:
        detail = "Price has not touched or reacted from a valid M15 Order Block or Fair Value Gap yet"
        failed.append(f"✗ {detail}")
        return _invalid(direction, 25, passed, failed, _checklist(PASSED, h4_detail, FAILED, detail))

    m15_detail = f"Price touched an M15 {m15_poi.kind.capitalize()} {m15_poi.zone_type} ({m15_poi.low:.5f}-{m15_poi.high:.5f})"

    # Step 3 -- POI alignment (H4 and M15 zones must be the same kind).
    wanted_kind = "bearish" if direction == "sell" else "bullish"
    if m15_poi.kind != wanted_kind:
        align_detail = f"M15 {m15_poi.kind.capitalize()} {m15_poi.zone_type} does not align with the H4 {poi_label} zone"
        failed.append(f"✗ {align_detail}")
        return _invalid(
            direction, 50, passed, failed,
            _checklist(PASSED, h4_detail, PASSED, m15_detail, FAILED, align_detail),
        )

    align_detail = f"M15 {wanted_kind.capitalize()} {m15_poi.zone_type} matches the H4 {poi_label} zone"
    passed.append(
        f"✓ Price touched a matching M15 {wanted_kind.capitalize()} {m15_poi.zone_type} "
        f"({m15_poi.low:.5f}-{m15_poi.high:.5f}) -- aligned with H4"
    )

    # Step 4 -- risk management. SL beyond the M15 POI used for entry.
    entry = (m15_poi.high + m15_poi.low) / 2
    poi_height = max(m15_poi.high - m15_poi.low, 1e-9)
    buffer = poi_height * SL_BUFFER_PCT
    stop_loss = m15_poi.high + buffer if direction == "sell" else m15_poi.low - buffer

    # TP = the next M15 Order Block or Fair Value Gap, opposite kind.
    target = _nearest_opposite_poi(m15, direction)
    target_label = "Bullish" if direction == "sell" else "Bearish"
    if target is not None:
        take_profit_candidate = target.high if direction == "sell" else target.low
        wrong_side = (direction == "sell" and take_profit_candidate >= entry) or (
            direction == "buy" and take_profit_candidate <= entry
        )
        if wrong_side:
            target = None

    if target is None:
        entry_detail = f"No opposite unmitigated M15 {target_label} Order Block or Fair Value Gap found yet as a target"
        failed.append(f"✗ {entry_detail}")
        return _invalid(
            direction, 75, passed, failed,
            _checklist(PASSED, h4_detail, PASSED, m15_detail, PASSED, align_detail, FAILED, entry_detail),
        )

    take_profit = target.high if direction == "sell" else target.low
    entry_detail = f"Next opposite M15 {target_label} {target.zone_type} found as target ({target.low:.5f}-{target.high:.5f})"
    passed.append(f"✓ {entry_detail}")

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
        "ruleChecks": _checklist(PASSED, h4_detail, PASSED, m15_detail, PASSED, align_detail, PASSED, entry_detail),
        "suggestedEntry": entry,
        "stopLoss": stop_loss,
        "takeProfit": take_profit,
        "riskReward": risk_reward,
        "recommendation": "TAKE",
    }
