"""Unit tests for the Personal Averaging Strategy (Sprint 18) -- the
user's own 5-rule checklist turned into a pure, deterministic engine.
Builds SmcAnalysis/OrderBlock/FairValueGap/Candle fixtures directly, no
raw candle-list parsing needed, matching the existing test style for
``htf_ltf_ob_strategy``.
"""
from __future__ import annotations

import pytest

from app.chart.candle_smc_engine import Candle, FairValueGap, OrderBlock, SmcAnalysis
from app.chart.personal_averaging_strategy import (
    RULE_ADD_ON,
    RULE_DAILY_BIAS,
    RULE_ENTRY_TIMING,
    RULE_M15_POI,
    compute_break_even_price,
    daily_bias,
    validate_personal_averaging,
)


def _daily(is_bullish: bool) -> list[Candle]:
    if is_bullish:
        return [Candle(time="d0", open=1.0, high=1.02, low=0.99, close=1.015)]
    return [Candle(time="d0", open=1.015, high=1.02, low=0.99, close=1.0)]


def _smc(current_price: float, **kwargs) -> SmcAnalysis:
    defaults = dict(trend="Ranging", structure="Ranging", current_price=current_price)
    defaults.update(kwargs)
    return SmcAnalysis(**defaults)


def _ob(kind: str, low: float, high: float) -> OrderBlock:
    return OrderBlock(index=0, time="t", kind=kind, high=high, low=low)


def _fvg(kind: str, bottom: float, top: float) -> FairValueGap:
    return FairValueGap(start_index=0, end_index=2, kind=kind, top=top, bottom=bottom)


# -- Step 1: Daily Bias --------------------------------------------------

def test_daily_bias_bullish_candle_is_buy():
    assert daily_bias(_daily(True)) == "buy"


def test_daily_bias_bearish_candle_is_sell():
    assert daily_bias(_daily(False)) == "sell"


def test_daily_bias_none_when_no_candles():
    assert daily_bias([]) is None


def test_no_daily_candle_is_invalid_zero_confidence():
    result = validate_personal_averaging([], None)
    assert result["tradeStatus"] == "INVALID"
    assert result["direction"] is None
    assert result["confidence"] == 0
    assert result["recommendation"] == "WAIT"
    checks = {c["rule"]: c["status"] for c in result["ruleChecks"]}
    assert checks[RULE_DAILY_BIAS] == "FAILED"
    assert checks[RULE_M15_POI] == "NOT_CHECKED"


# -- Step 2: M15 POI matching daily bias ---------------------------------

def test_bullish_daily_no_m15_data_is_invalid():
    result = validate_personal_averaging(_daily(True), None)
    assert result["tradeStatus"] == "INVALID"
    assert result["direction"] == "buy"
    assert result["dailyBias"] == "BUY"
    assert result["confidence"] == 25


def test_bullish_daily_but_only_bearish_m15_poi_is_invalid():
    # Wrong-kind zone touched -- doesn't count as a matching M15 POI.
    m15 = _smc(current_price=1.115, order_blocks=[_ob("bearish", 1.10, 1.12)])
    result = validate_personal_averaging(_daily(True), m15)
    assert result["tradeStatus"] == "INVALID"
    checks = {c["rule"]: c["status"] for c in result["ruleChecks"]}
    assert checks[RULE_M15_POI] == "FAILED"


# -- Step 3: Entry timing (near end, not beginning, of the zone) --------

def test_bullish_poi_touched_near_beginning_top_is_invalid():
    # Bullish OB spans 1.10-1.12; price at 1.118 is in the *upper* half
    # (near the top = "beginning" for a buy approached from above).
    m15 = _smc(current_price=1.118, order_blocks=[_ob("bullish", 1.10, 1.12)])
    result = validate_personal_averaging(_daily(True), m15)
    assert result["tradeStatus"] == "INVALID"
    checks = {c["rule"]: c["status"] for c in result["ruleChecks"]}
    assert checks[RULE_M15_POI] == "PASSED"
    assert checks[RULE_ENTRY_TIMING] == "FAILED"


def test_bullish_poi_touched_near_end_bottom_is_valid_take():
    # Same zone, price at 1.103 -- lower half = "near the end" for a buy.
    m15 = _smc(current_price=1.103, order_blocks=[_ob("bullish", 1.10, 1.12)])
    result = validate_personal_averaging(_daily(True), m15)
    assert result["tradeStatus"] == "VALID"
    assert result["direction"] == "buy"
    assert result["recommendation"] == "TAKE"
    assert result["addOnSignal"] is False
    assert result["stopLoss"] is None
    assert result["takeProfit"] is None
    checks = {c["rule"]: c["status"] for c in result["ruleChecks"]}
    assert checks[RULE_DAILY_BIAS] == "PASSED"
    assert checks[RULE_M15_POI] == "PASSED"
    assert checks[RULE_ENTRY_TIMING] == "PASSED"
    assert checks[RULE_ADD_ON] == "NOT_CHECKED"


def test_bearish_poi_near_end_top_is_valid_take():
    # Bearish OB spans 1.20-1.22; "end" for a sell (approached from
    # below) is the *top* half.
    m15 = _smc(current_price=1.217, order_blocks=[_ob("bearish", 1.20, 1.22)])
    result = validate_personal_averaging(_daily(False), m15)
    assert result["tradeStatus"] == "VALID"
    assert result["direction"] == "sell"
    assert result["recommendation"] == "TAKE"


def test_fvg_counts_as_valid_poi_too():
    m15 = _smc(current_price=1.181, fair_value_gaps=[_fvg("bullish", 1.180, 1.185)])
    result = validate_personal_averaging(_daily(True), m15)
    assert result["tradeStatus"] == "VALID"


# -- Step 4: Add-on entry -------------------------------------------------

def test_addon_signal_fires_when_open_trade_in_loss():
    m15 = _smc(current_price=1.103, order_blocks=[_ob("bullish", 1.10, 1.12)])
    result = validate_personal_averaging(_daily(True), m15, open_trade_in_loss=True)
    assert result["tradeStatus"] == "VALID"
    assert result["recommendation"] == "ADD"
    assert result["addOnSignal"] is True
    checks = {c["rule"]: c["status"] for c in result["ruleChecks"]}
    assert checks[RULE_ADD_ON] == "PASSED"


def test_no_addon_signal_when_no_open_trade():
    m15 = _smc(current_price=1.103, order_blocks=[_ob("bullish", 1.10, 1.12)])
    result = validate_personal_averaging(_daily(True), m15, open_trade_in_loss=False)
    assert result["recommendation"] == "TAKE"
    assert result["addOnSignal"] is False


# -- Break-even price calculator ------------------------------------------

def test_break_even_two_equal_size_buys_is_the_average():
    price = compute_break_even_price("buy", [(1.1000, 1.0), (1.0950, 1.0)])
    assert price == pytest.approx(1.0975)


def test_break_even_two_equal_size_sells_is_the_average():
    price = compute_break_even_price("sell", [(1.2000, 1.0), (1.2050, 1.0)])
    assert price == pytest.approx(1.2025)


def test_break_even_with_small_target_profit_shifts_buy_price_down():
    # For a buy, needing a bit of profit means you can exit at a
    # slightly LOWER price than plain breakeven (size=2 total).
    breakeven = compute_break_even_price("buy", [(1.10, 1.0), (1.09, 1.0)])
    with_profit = compute_break_even_price("buy", [(1.10, 1.0), (1.09, 1.0)], target_net_profit_per_unit=0.01)
    assert with_profit > breakeven


def test_break_even_unequal_sizes_is_weighted():
    # Bigger size at 1.10 should pull the break-even closer to 1.10
    # than the plain (unweighted) average of 1.05.
    price = compute_break_even_price("buy", [(1.10, 2.0), (1.00, 1.0)])
    assert price == pytest.approx((1.10 * 2 + 1.00 * 1) / 3)
    assert price > 1.05


def test_break_even_raises_on_empty_entries():
    with pytest.raises(ValueError):
        compute_break_even_price("buy", [])


def test_break_even_raises_on_bad_direction():
    with pytest.raises(ValueError):
        compute_break_even_price("sideways", [(1.0, 1.0)])
