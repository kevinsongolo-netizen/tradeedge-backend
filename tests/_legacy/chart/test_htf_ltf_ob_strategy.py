"""Unit tests for the active H4->M15 POI strategy (v2 -- the user's
formal written spec: Order Block OR Fair Value Gap on both timeframes,
direction alignment required, M15-based take-profit target). Builds
SmcAnalysis/OrderBlock/FairValueGap fixtures directly -- no candle data
needed, matching the "pure function" testability the module promises.
"""
from __future__ import annotations

from app.chart.candle_smc_engine import FairValueGap, OrderBlock, SmcAnalysis
from app._legacy.chart.htf_ltf_ob_strategy import validate_h4_m15_ob


def _smc(current_price: float, **kwargs) -> SmcAnalysis:
    defaults = dict(trend="Ranging", structure="Ranging", current_price=current_price)
    defaults.update(kwargs)
    return SmcAnalysis(**defaults)


def _ob(kind: str, low: float, high: float) -> OrderBlock:
    return OrderBlock(index=0, time="t", kind=kind, high=high, low=low)


def _fvg(kind: str, bottom: float, top: float) -> FairValueGap:
    return FairValueGap(start_index=0, end_index=2, kind=kind, top=top, bottom=bottom)


def test_no_h4_poi_touch_is_invalid_zero_confidence():
    h4 = _smc(current_price=1.0)  # no order blocks or FVGs at all
    result = validate_h4_m15_ob(h4, None)
    assert result["tradeStatus"] == "INVALID"
    assert result["direction"] is None
    assert result["confidence"] == 0
    assert result["recommendation"] == "WAIT"


def test_rule_checks_all_not_checked_downstream_when_h4_fails():
    h4 = _smc(current_price=1.0)
    result = validate_h4_m15_ob(h4, None)
    checks = {c["rule"]: c["status"] for c in result["ruleChecks"]}
    assert checks["H4 Order Block/FVG"] == "FAILED"
    assert checks["M15 Order Block/FVG"] == "NOT_CHECKED"
    assert checks["POI Alignment"] == "NOT_CHECKED"
    assert checks["Entry / SL / TP"] == "NOT_CHECKED"


def test_h4_bearish_ob_touch_no_m15_data():
    h4_ob = _ob("bearish", 1.10, 1.12)
    h4 = _smc(current_price=1.11, order_blocks=[h4_ob])
    result = validate_h4_m15_ob(h4, None)
    assert result["tradeStatus"] == "INVALID"
    assert result["direction"] == "sell"
    assert result["confidence"] == 25


def test_h4_bullish_fvg_touch_counts_as_h4_poi():
    h4_fvg = _fvg("bullish", 1.1800, 1.1850)
    h4 = _smc(current_price=1.1820, fair_value_gaps=[h4_fvg])
    result = validate_h4_m15_ob(h4, None)
    assert result["tradeStatus"] == "INVALID"  # no M15 data yet
    assert result["direction"] == "buy"
    assert any("Fair Value Gap" in r for r in result["reasonsPassed"])


def test_m15_not_touched_yet_is_invalid():
    h4_ob = _ob("bearish", 1.10, 1.12)
    h4 = _smc(current_price=1.11, order_blocks=[h4_ob])
    m15 = _smc(current_price=1.50)  # nowhere near any zone
    result = validate_h4_m15_ob(h4, m15)
    assert result["tradeStatus"] == "INVALID"
    assert result["direction"] == "sell"
    assert result["confidence"] == 25
    assert any("M15" in r for r in result["reasonsFailed"])


def test_m15_touched_but_wrong_direction_is_misaligned():
    h4_ob = _ob("bearish", 1.10, 1.12)
    h4 = _smc(current_price=1.11, order_blocks=[h4_ob])
    m15_wrong = _ob("bullish", 1.099, 1.101)  # bullish touch, but H4 says sell
    m15 = _smc(current_price=1.100, order_blocks=[m15_wrong])
    result = validate_h4_m15_ob(h4, m15)
    assert result["tradeStatus"] == "INVALID"
    assert result["confidence"] == 50
    assert any("align" in r for r in result["reasonsFailed"])
    checks = {c["rule"]: c["status"] for c in result["ruleChecks"]}
    # The M15 POI step itself PASSED (a zone was touched) -- it's
    # alignment specifically that failed, which is its own separate
    # rule per the user's spec (not folded into "M15 POI").
    assert checks["H4 Order Block/FVG"] == "PASSED"
    assert checks["M15 Order Block/FVG"] == "PASSED"
    assert checks["POI Alignment"] == "FAILED"
    assert checks["Entry / SL / TP"] == "NOT_CHECKED"


def test_no_opposite_m15_target_is_invalid():
    h4_ob = _ob("bearish", 1.20, 1.205)
    h4 = _smc(current_price=1.202, order_blocks=[h4_ob])
    m15_ob = _ob("bearish", 1.2010, 1.2020)
    m15 = _smc(current_price=1.2015, order_blocks=[m15_ob])  # no bullish target anywhere
    result = validate_h4_m15_ob(h4, m15)
    assert result["tradeStatus"] == "INVALID"
    assert result["confidence"] == 75
    assert any("target" in r for r in result["reasonsFailed"])


def test_full_valid_sell_ob_h4_ob_m15_ob_target():
    h4_ob = _ob("bearish", 1.2000, 1.2050)
    h4 = _smc(current_price=1.2020, order_blocks=[h4_ob])
    m15_entry_ob = _ob("bearish", 1.2010, 1.2020)
    m15_target_ob = _ob("bullish", 1.1800, 1.1850)
    m15 = _smc(
        current_price=1.2015,
        order_blocks=[m15_entry_ob, m15_target_ob],
        nearest_unmitigated_ob_bullish=m15_target_ob,
    )
    result = validate_h4_m15_ob(h4, m15)
    assert result["tradeStatus"] == "VALID"
    assert result["direction"] == "sell"
    assert result["recommendation"] == "TAKE"
    assert result["confidence"] == 100
    assert result["suggestedEntry"] == (1.2010 + 1.2020) / 2
    assert result["stopLoss"] > m15_entry_ob.high
    assert result["takeProfit"] == m15_target_ob.high  # near edge, approached from above
    assert result["takeProfit"] < result["suggestedEntry"]
    assert result["riskReward"] > 0
    checks = {c["rule"]: c["status"] for c in result["ruleChecks"]}
    assert checks["H4 Order Block/FVG"] == "PASSED"
    assert checks["M15 Order Block/FVG"] == "PASSED"
    assert checks["POI Alignment"] == "PASSED"
    assert checks["Entry / SL / TP"] == "PASSED"
    assert len(result["ruleChecks"]) == 4
    assert all("rule" in c and "status" in c and "detail" in c for c in result["ruleChecks"])


def test_full_valid_buy_using_fvg_on_both_timeframes():
    h4_fvg = _fvg("bullish", 1.1800, 1.1850)
    h4 = _smc(current_price=1.1820, fair_value_gaps=[h4_fvg])
    m15_entry_fvg = _fvg("bullish", 1.1805, 1.1815)
    m15_target_fvg = _fvg("bearish", 1.2000, 1.2050)
    m15 = _smc(
        current_price=1.1810,
        fair_value_gaps=[m15_entry_fvg, m15_target_fvg],
        nearest_unmitigated_fvg_bearish=m15_target_fvg,
    )
    result = validate_h4_m15_ob(h4, m15)
    assert result["tradeStatus"] == "VALID"
    assert result["direction"] == "buy"
    assert result["suggestedEntry"] == (1.1805 + 1.1815) / 2
    assert result["stopLoss"] < m15_entry_fvg.bottom
    assert result["takeProfit"] == m15_target_fvg.bottom  # near edge, approached from below
    assert result["takeProfit"] > result["suggestedEntry"]
    assert result["riskReward"] > 0
    assert any("Fair Value Gap" in r for r in result["reasonsPassed"])


def test_mixed_ob_and_fvg_target_picks_the_closer_one():
    # Entry (sell) at ~1.2015. Two candidate bullish targets below:
    # an FVG much closer, and an OB further away -- the closer one
    # ("the next" zone structurally) should win.
    h4_ob = _ob("bearish", 1.2000, 1.2050)
    h4 = _smc(current_price=1.2020, order_blocks=[h4_ob])
    m15_entry_ob = _ob("bearish", 1.2010, 1.2020)
    close_target_fvg = _fvg("bullish", 1.1950, 1.1960)
    far_target_ob = _ob("bullish", 1.1800, 1.1850)
    m15 = _smc(
        current_price=1.2015,
        order_blocks=[m15_entry_ob, far_target_ob],
        fair_value_gaps=[close_target_fvg],
        nearest_unmitigated_ob_bullish=far_target_ob,
        nearest_unmitigated_fvg_bullish=close_target_fvg,
    )
    result = validate_h4_m15_ob(h4, m15)
    assert result["tradeStatus"] == "VALID"
    assert result["takeProfit"] == close_target_fvg.top


def test_target_on_wrong_side_is_rejected_not_nonsensical():
    h4_ob = _ob("bearish", 1.2000, 1.2050)
    h4 = _smc(current_price=1.2020, order_blocks=[h4_ob])
    m15_entry_ob = _ob("bearish", 1.2010, 1.2020)
    wrong_side_target = _ob("bullish", 1.2100, 1.2150)  # ABOVE entry -- can't be a sell target
    m15 = _smc(
        current_price=1.2015,
        order_blocks=[m15_entry_ob, wrong_side_target],
        nearest_unmitigated_ob_bullish=wrong_side_target,
    )
    result = validate_h4_m15_ob(h4, m15)
    assert result["tradeStatus"] == "INVALID"
    assert any("target" in r for r in result["reasonsFailed"])
