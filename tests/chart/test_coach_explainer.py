"""Unit tests for Level 3 (app/chart/coach_explainer.py).

Rewritten to build on the ACTIVE strategy's own validation dict
(``validate_h4_m15_ob``) instead of the retired Classic Bias validator
-- this module is now a thin narrator over that dict, so its tests
should exercise it the same way the real app does.
"""
from app.chart.candle_smc_engine import FairValueGap, OrderBlock, SmcAnalysis
from app.chart.coach_explainer import explain
from app.chart.htf_ltf_ob_strategy import validate_h4_m15_ob
from app.schemas.chart import ChartAnalysis, ZoneOut


def _smc(current_price: float, **kwargs) -> SmcAnalysis:
    defaults = dict(trend="Ranging", structure="Ranging", current_price=current_price)
    defaults.update(kwargs)
    return SmcAnalysis(**defaults)


def _ob(kind: str, low: float, high: float) -> OrderBlock:
    return OrderBlock(index=0, time="t", kind=kind, high=high, low=low)


def _analysis(**overrides) -> ChartAnalysis:
    defaults = dict(
        source="candles",
        trend="Bullish",
        structure="Bullish",
        currentPriceContext="Inside Bullish Order Block (1.09000-1.09500)",
        liquidity="Equal highs resting above price (1 cluster(s))",
        latestEvent="Bullish CHOCH detected",
        fvgStatus="Bullish FVG unmitigated (1.0940-1.0960)",
        premiumDiscount="Discount",
        bias="BUY",
        confidence=92,
        zones=[],
        entryZone=ZoneOut(kind="bullish", zoneType="Order Block", high=1.0950, low=1.0900, mitigated=False),
        notes=[],
        isPlaceholder=False,
    )
    defaults.update(overrides)
    return ChartAnalysis(**defaults)


def _valid_sell_validation() -> dict:
    h4_ob = _ob("bearish", 1.2000, 1.2050)
    h4 = _smc(current_price=1.2020, order_blocks=[h4_ob])
    m15_entry_ob = _ob("bearish", 1.2010, 1.2020)
    m15_target_ob = _ob("bullish", 1.1800, 1.1850)
    m15 = _smc(
        current_price=1.2015,
        order_blocks=[m15_entry_ob, m15_target_ob],
        nearest_unmitigated_ob_bullish=m15_target_ob,
    )
    return validate_h4_m15_ob(h4, m15)


def _wait_validation() -> dict:
    h4 = _smc(current_price=1.0)  # no order blocks or FVGs at all -> H4 POI fails immediately
    return validate_h4_m15_ob(h4, None)


def test_valid_trade_gets_directional_headline_and_explains_every_rule():
    validation = _valid_sell_validation()
    result = explain(_analysis(), validation)
    assert result["headline"] == "SELL ANALYSIS"
    assert result["recommendation"] == "SELL"
    # Spec requirement: always explain WHY, multiple sentences, not just "Sell".
    assert len(result["explanation"]) >= 3
    assert all(isinstance(s, str) and s for s in result["explanation"])
    # Every rule the strategy checked shows up in the narration -- no
    # separate/duplicate scoring of trend, BOS, CHOCH, etc.
    joined = " ".join(result["explanation"])
    assert "H4 Order Block/FVG" in joined
    assert "M15 Order Block/FVG" in joined
    assert "POI Alignment" in joined


def test_wait_result_gets_wait_headline_and_names_the_failed_rule():
    validation = _wait_validation()
    result = explain(_analysis(), validation)
    assert result["headline"] == "WAIT"
    assert result["recommendation"] == "WAIT"
    joined = " ".join(result["explanation"])
    assert "H4 Order Block/FVG" in joined


def test_confidence_breakdown_mirrors_the_strategys_own_rule_checks():
    validation = _valid_sell_validation()
    result = explain(_analysis(), validation)
    breakdown = result["confidence"]
    for key in ("h4_poi", "m15_poi", "poi_alignment", "entry_target", "overall"):
        assert 0 <= breakdown[key] <= 100, f"{key} out of range: {breakdown[key]}"
    assert breakdown["overall"] == validation["confidence"]


def test_confidence_breakdown_is_all_zero_when_first_rule_fails():
    validation = _wait_validation()
    result = explain(_analysis(), validation)
    breakdown = result["confidence"]
    assert breakdown["h4_poi"] == 0
    assert breakdown["m15_poi"] == 0
    assert breakdown["poi_alignment"] == 0
    assert breakdown["entry_target"] == 0
    assert breakdown["overall"] == 0


def test_valid_trade_scores_higher_overall_than_a_wait():
    valid_result = explain(_analysis(), _valid_sell_validation())
    wait_result = explain(_analysis(), _wait_validation())
    assert valid_result["confidence"]["overall"] > wait_result["confidence"]["overall"]
