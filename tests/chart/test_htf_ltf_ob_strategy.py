"""Unit tests for the active H4->M15 Order Block strategy (the user's
own rules, see app/chart/htf_ltf_ob_strategy.py). Constructs SmcAnalysis/
OrderBlock fixtures directly -- no candle data needed, matching the
"pure function" testability the module docstring promises."""
from __future__ import annotations

from app.chart.candle_smc_engine import OrderBlock, SmcAnalysis
from app.chart.htf_ltf_ob_strategy import validate_h4_m15_ob


def _smc(**kwargs) -> SmcAnalysis:
    defaults = dict(trend="Ranging", structure="Ranging", current_price=1.0)
    defaults.update(kwargs)
    return SmcAnalysis(**defaults)


def _ob(kind: str, low: float, high: float) -> OrderBlock:
    return OrderBlock(index=0, time="t", kind=kind, high=high, low=low)


def test_no_h4_touch_is_invalid_with_zero_confidence():
    h4 = _smc(price_in_order_block=None)
    result = validate_h4_m15_ob(h4, None)
    assert result["tradeStatus"] == "INVALID"
    assert result["direction"] is None
    assert result["confidence"] == 0
    assert result["recommendation"] == "WAIT"


def test_h4_bearish_touch_no_m15_data_is_invalid_but_direction_known():
    h4_ob = _ob("bearish", low=1.10, high=1.12)
    h4 = _smc(price_in_order_block=h4_ob)
    result = validate_h4_m15_ob(h4, None)
    assert result["tradeStatus"] == "INVALID"
    assert result["direction"] == "sell"
    assert any("M15" in r for r in result["reasonsFailed"])


def test_h4_bearish_touch_m15_wrong_kind_is_invalid():
    h4_ob = _ob("bearish", low=1.10, high=1.12)
    h4 = _smc(price_in_order_block=h4_ob)
    m15_ob = _ob("bullish", low=1.099, high=1.101)  # wrong kind for a sell setup
    m15 = _smc(price_in_order_block=m15_ob)
    result = validate_h4_m15_ob(h4, m15)
    assert result["tradeStatus"] == "INVALID"
    assert result["direction"] == "sell"


def test_h4_and_m15_touch_but_no_opposite_target_is_invalid():
    h4_ob = _ob("bearish", low=1.10, high=1.12)
    h4 = _smc(price_in_order_block=h4_ob, nearest_unmitigated_ob_bullish=None)
    m15_ob = _ob("bearish", low=1.099, high=1.101)
    m15 = _smc(price_in_order_block=m15_ob)
    result = validate_h4_m15_ob(h4, m15)
    assert result["tradeStatus"] == "INVALID"
    assert result["confidence"] == 67
    assert any("target" in r for r in result["reasonsFailed"])


def test_full_valid_sell_setup_entry_sl_tp():
    h4_bear_ob = _ob("bearish", low=1.2000, high=1.2050)   # touched -> candidate SELL
    h4_bull_target = _ob("bullish", low=1.1800, high=1.1850)  # opposite target, below price
    h4 = _smc(
        price_in_order_block=h4_bear_ob,
        nearest_unmitigated_ob_bullish=h4_bull_target,
    )
    m15_ob = _ob("bearish", low=1.2010, high=1.2020)  # the actual entry trigger
    m15 = _smc(price_in_order_block=m15_ob)

    result = validate_h4_m15_ob(h4, m15)

    assert result["tradeStatus"] == "VALID"
    assert result["direction"] == "sell"
    assert result["recommendation"] == "TAKE"
    assert result["confidence"] == 100

    # Entry = M15 OB midpoint
    assert result["suggestedEntry"] == (1.2010 + 1.2020) / 2
    # Stop loss just above the M15 OB's top
    assert result["stopLoss"] > m15_ob.high
    # Take profit = top ("beginning") of the opposite H4 bullish OB
    assert result["takeProfit"] == h4_bull_target.high
    assert result["takeProfit"] < result["suggestedEntry"]  # target is below entry for a sell
    assert result["riskReward"] > 0


def test_full_valid_buy_setup_entry_sl_tp():
    h4_bull_ob = _ob("bullish", low=1.1800, high=1.1850)      # touched -> candidate BUY
    h4_bear_target = _ob("bearish", low=1.2000, high=1.2050)  # opposite target, above price
    h4 = _smc(
        price_in_order_block=h4_bull_ob,
        nearest_unmitigated_ob_bearish=h4_bear_target,
    )
    m15_ob = _ob("bullish", low=1.1810, high=1.1820)
    m15 = _smc(price_in_order_block=m15_ob)

    result = validate_h4_m15_ob(h4, m15)

    assert result["tradeStatus"] == "VALID"
    assert result["direction"] == "buy"
    assert result["suggestedEntry"] == (1.1810 + 1.1820) / 2
    assert result["stopLoss"] < m15_ob.low
    assert result["takeProfit"] == h4_bear_target.low
    assert result["takeProfit"] > result["suggestedEntry"]
    assert result["riskReward"] > 0


def test_target_on_wrong_side_is_rejected_not_nonsensical():
    # Opposite OB exists but sits ABOVE entry for a sell -- physically
    # can't be a valid downside target, must be treated as "no target".
    h4_bear_ob = _ob("bearish", low=1.2000, high=1.2050)
    h4_bull_target_wrong_side = _ob("bullish", low=1.2100, high=1.2150)  # above price!
    h4 = _smc(
        price_in_order_block=h4_bear_ob,
        nearest_unmitigated_ob_bullish=h4_bull_target_wrong_side,
    )
    m15_ob = _ob("bearish", low=1.2010, high=1.2020)
    m15 = _smc(price_in_order_block=m15_ob)

    result = validate_h4_m15_ob(h4, m15)

    assert result["tradeStatus"] == "INVALID"
    assert any("target" in r for r in result["reasonsFailed"])
