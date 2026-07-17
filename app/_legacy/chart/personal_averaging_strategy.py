"""Personal Averaging Strategy (Sprint 18) -- a second, user-designed
strategy built from Moma's own Pre-Trade Checklist rules, offered as an
alternative to the H4->M15 POI engine in ``htf_ltf_ob_strategy.py``.

Official rules, exactly as written by the user on the Checklist page:

1. "First check daily candle if it is bullish buy" -- Step 1, Daily
   Bias: a bullish daily candle means only BUY setups are considered
   that day; a bearish daily candle means only SELL setups. This is
   the one and only direction filter -- there is no H4 POI step here.

2. "Enter at any POI but not in the beginning of the block but near
   the [end] of the end" -- Step 2 + 3: price must be touching an M15
   Order Block or Fair Value Gap matching the daily bias, AND price
   must have traded into the *far* half of that zone (the half
   reached only after a deeper retracement), not just clipped the
   near edge.

3. "2nd entry same direction same size but enter only when 15m POI
   goes bullish" -- Step 4, Add-On Entry: only evaluated once the
   first entry is already open and floating in a loss. Fires when a
   *fresh* M15 POI matching the same direction has been touched,
   signalling it's time to place the second, equal-size entry.

4. "when i am in losing running trade i must not close one win or one
   lost i must at least close 1 win same time with 1 lost that will
   stop at zero os with a small profit never close in lost" -- this is
   an exit/money-management rule, not an entry rule, so it isn't part
   of the VALID/WAIT decision. ``compute_break_even_price`` below turns
   it into a concrete number: the price at which the open entries
   (equal size or not) net to breakeven or a chosen small target
   profit, so "never close in lost" has an actual price level to
   watch for instead of being a vague intention.

5. "This is a kind of saving because the profit is very small don't
   rely on this account" -- a sizing/expectation note from the user,
   not something this engine can check; surfaced as-is in the coach
   narration layer instead.

Deliberately NOT part of this strategy: any fixed stop loss or take
profit. The user runs this without a stop loss by design -- see the
``break_even_price`` helper and the separate margin-buffer feature
(``app/services/account_margin_service.py``) for the real safety net
that replaces a stop loss here.

Like ``validate_h4_m15_ob``, this is a pure function of already-parsed
SMC analysis (plus one raw daily candle) -- no I/O, no randomness.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.chart.candle_smc_engine import Candle, FairValueGap, OrderBlock, SmcAnalysis

STRATEGY_NAME = "Personal Averaging Strategy (Daily Bias + M15 POI, no fixed SL/TP)"

PASSED = "PASSED"
FAILED = "FAILED"
NOT_CHECKED = "NOT_CHECKED"

RULE_DAILY_BIAS = "Daily Bias"
RULE_M15_POI = "M15 Order Block/FVG"
RULE_ENTRY_TIMING = "Entry Timing (near end of zone)"
RULE_ADD_ON = "Add-On Entry (2nd position)"

_NOT_CHECKED_DETAIL = "Not checked -- an earlier rule must pass first"


@dataclass
class Poi:
    kind: str  # "bullish" | "bearish"
    zone_type: str  # "Order Block" | "Fair Value Gap"
    low: float
    high: float


def _poi_from_ob(ob: OrderBlock) -> Poi:
    return Poi(kind=ob.kind, zone_type="Order Block", low=ob.low, high=ob.high)


def _poi_from_fvg(fvg: FairValueGap) -> Poi:
    return Poi(kind=fvg.kind, zone_type="Fair Value Gap", low=fvg.bottom, high=fvg.top)


def daily_bias(daily_candles: list[Candle]) -> str | None:
    """Step 1 -- "First check daily candle if it is bullish buy". Only
    the most recent completed daily candle matters. Returns "buy" for
    a bullish candle (close >= open), "sell" for bearish, or None if no
    daily candle was supplied at all."""
    if not daily_candles:
        return None
    last = daily_candles[-1]
    return "buy" if last.is_bullish else "sell"


def _touched_poi_matching(smc: SmcAnalysis, wanted_kind: str) -> Poi | None:
    """Like ``htf_ltf_ob_strategy._touched_poi``, but restricted to a
    single wanted kind -- this strategy already knows its direction
    from the daily bias, it isn't deriving direction from the zone."""
    current = smc.current_price
    for ob in reversed(smc.order_blocks):
        if not ob.mitigated and ob.kind == wanted_kind and ob.low <= current <= ob.high:
            return _poi_from_ob(ob)
    for gap in reversed(smc.fair_value_gaps):
        if not gap.mitigated and gap.kind == wanted_kind and gap.bottom <= current <= gap.top:
            return _poi_from_fvg(gap)
    return None


def _is_near_end_of_zone(poi: Poi, current_price: float, direction: str) -> bool:
    """Rule 2's "not in the beginning of the block but near the end".

    A buy zone (bullish OB/FVG) sits below/at price and is approached
    from above -- the "beginning" is the top edge (first touched), the
    "end" is the bottom edge (only reached after a deeper pullback).
    A sell zone is the mirror image. "Near the end" = price has traded
    into the far half of the zone, not just clipped the near edge."""
    midpoint = (poi.low + poi.high) / 2
    if direction == "buy":
        return current_price <= midpoint
    return current_price >= midpoint


def _checklist(
    bias_status: str,
    bias_detail: str,
    poi_status: str = NOT_CHECKED,
    poi_detail: str = _NOT_CHECKED_DETAIL,
    timing_status: str = NOT_CHECKED,
    timing_detail: str = _NOT_CHECKED_DETAIL,
    addon_status: str = NOT_CHECKED,
    addon_detail: str = _NOT_CHECKED_DETAIL,
) -> list[dict]:
    return [
        {"rule": RULE_DAILY_BIAS, "status": bias_status, "detail": bias_detail},
        {"rule": RULE_M15_POI, "status": poi_status, "detail": poi_detail},
        {"rule": RULE_ENTRY_TIMING, "status": timing_status, "detail": timing_detail},
        {"rule": RULE_ADD_ON, "status": addon_status, "detail": addon_detail},
    ]


def _invalid(direction: str | None, bias: str | None, confidence: int, rule_checks: list[dict]) -> dict:
    return {
        "tradeStatus": "INVALID",
        "direction": direction,
        "confidence": confidence,
        "reasonsPassed": [],
        "reasonsFailed": [c["detail"] for c in rule_checks if c["status"] == FAILED],
        "ruleChecks": rule_checks,
        "suggestedEntry": None,
        "stopLoss": None,
        "takeProfit": None,
        "riskReward": None,
        "recommendation": "WAIT",
        "strategy": STRATEGY_NAME,
        "dailyBias": bias.upper() if bias else None,
        "addOnSignal": False,
        "breakEvenPrice": None,
    }


def validate_personal_averaging(
    daily_candles: list[Candle],
    m15: SmcAnalysis | None,
    *,
    open_trade_in_loss: bool = False,
) -> dict:
    """Pure function -- same output shape family as
    ``validate_h4_m15_ob`` (``TradeValidationResult``-compatible dict),
    plus the Sprint 18 fields (``strategy``, ``dailyBias``,
    ``addOnSignal``, ``breakEvenPrice``).

    ``open_trade_in_loss`` is supplied by the caller (Pre-Trade Check /
    Chart Analysis Engine already knows whether the user has an open
    position on this pair) -- when True and rules 1-3 above are met
    again, that's rule 3's "2nd entry" add-on signal rather than a
    fresh first entry.
    """
    # Step 1 -- Daily Bias.
    bias = daily_bias(daily_candles)
    if bias is None:
        detail = "No daily candle supplied -- can't determine daily bias"
        return _invalid(None, None, 0, _checklist(FAILED, detail))

    bias_label = "Bullish" if bias == "buy" else "Bearish"
    bias_detail = f"Daily candle is {bias_label} -- only {bias.upper()} setups apply today"

    # Step 2 -- M15 POI matching the daily bias.
    if m15 is None:
        detail = "No M15 candle data supplied -- can't check for the M15 Point of Interest"
        return _invalid(bias, bias, 25, _checklist(PASSED, bias_detail, FAILED, detail))

    wanted_kind = "bullish" if bias == "buy" else "bearish"
    poi = _touched_poi_matching(m15, wanted_kind)
    if poi is None:
        detail = f"Price has not touched a matching M15 {wanted_kind.capitalize()} Order Block or Fair Value Gap yet"
        return _invalid(bias, bias, 25, _checklist(PASSED, bias_detail, FAILED, detail))

    poi_detail = f"Price touched an M15 {wanted_kind.capitalize()} {poi.zone_type} ({poi.low:.5f}-{poi.high:.5f})"

    # Step 3 -- Entry timing: near the end of the zone, not the beginning.
    if not _is_near_end_of_zone(poi, m15.current_price, bias):
        timing_detail = (
            "Price has only clipped the near edge of the zone -- wait for a deeper move "
            "toward the far side before entering (not the beginning of the block)"
        )
        return _invalid(
            bias, bias, 50,
            _checklist(PASSED, bias_detail, PASSED, poi_detail, FAILED, timing_detail),
        )

    timing_detail = "Price has traded into the far half of the zone -- near the end of the block, as required"

    # Step 4 -- Add-on entry: only meaningful once a first position is
    # already open and floating in a loss.
    if open_trade_in_loss:
        addon_detail = (
            f"A fresh matching M15 {wanted_kind.capitalize()} zone has been touched while the first "
            f"trade is floating in a loss -- rule 3's 2nd, same-size entry applies now"
        )
        checks = _checklist(
            PASSED, bias_detail, PASSED, poi_detail, PASSED, timing_detail, PASSED, addon_detail,
        )
        return {
            "tradeStatus": "VALID",
            "direction": bias,
            "confidence": 100,
            "reasonsPassed": [bias_detail, poi_detail, timing_detail, addon_detail],
            "reasonsFailed": [],
            "ruleChecks": checks,
            "suggestedEntry": m15.current_price,
            "stopLoss": None,
            "takeProfit": None,
            "riskReward": None,
            "recommendation": "ADD",
            "strategy": STRATEGY_NAME,
            "dailyBias": bias.upper(),
            "addOnSignal": True,
            "breakEvenPrice": None,
        }

    # Fresh first entry -- rules 1-3 all pass, no open position yet.
    checks = _checklist(
        PASSED, bias_detail, PASSED, poi_detail, PASSED, timing_detail,
        NOT_CHECKED, "Not checked -- no open position yet, this is the first entry",
    )
    return {
        "tradeStatus": "VALID",
        "direction": bias,
        "confidence": 100,
        "reasonsPassed": [bias_detail, poi_detail, timing_detail],
        "reasonsFailed": [],
        "ruleChecks": checks,
        "suggestedEntry": m15.current_price,
        "stopLoss": None,
        "takeProfit": None,
        "riskReward": None,
        "recommendation": "TAKE",
        "strategy": STRATEGY_NAME,
        "dailyBias": bias.upper(),
        "addOnSignal": False,
        "breakEvenPrice": None,
    }


def compute_break_even_price(
    direction: str,
    entries: list[tuple[float, float]],
    target_net_profit_per_unit: float = 0.0,
) -> float:
    """Rule 4 -- "never close in lost", made concrete: the price at
    which all open ``entries`` (list of ``(price, size)`` pairs -- size
    can be lots, units, or any consistent multiplier, they don't have
    to be equal) net to ``target_net_profit_per_unit`` (0.0 = exact
    breakeven; a small positive number = "stop at zero... with a small
    profit", per the user's own wording).

    Pure price/size math, direction-agnostic:

    * BUY:  combined P&L(price) = sum(size_i * (price - entry_i))
    * SELL: combined P&L(price) = sum(size_i * (entry_i - price))

    Solving for price at the target P&L gives the formulas below. With
    two equal-size entries (the user's own rule 3: "same size") and a
    target of exactly 0, this reduces to the simple average of the two
    entry prices -- as expected for a plain breakeven.
    """
    if not entries:
        raise ValueError("Need at least one (price, size) entry to compute a break-even price")
    total_size = sum(size for _, size in entries)
    if total_size <= 0:
        raise ValueError("Total size must be greater than 0")
    weighted_entry_sum = sum(price * size for price, size in entries)

    if direction == "buy":
        return (target_net_profit_per_unit + weighted_entry_sum) / total_size
    if direction == "sell":
        return (weighted_entry_sum - target_net_profit_per_unit) / total_size
    raise ValueError(f"direction must be 'buy' or 'sell', got {direction!r}")
