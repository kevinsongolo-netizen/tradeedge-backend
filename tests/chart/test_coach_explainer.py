"""Unit tests for Level 3 (app/chart/coach_explainer.py).

Rewritten (Sprint 18) to build on the ACTIVE strategy's own validation
dict (``validate_personal_averaging``) instead of the retired H4->M15
POI validator -- this module is a thin narrator over that dict, so its
tests exercise it the same way the real app does.
"""
from app.chart.candle_smc_engine import Candle, OrderBlock, SmcAnalysis
from app.chart.coach_explainer import explain
from app.chart.personal_averaging_strategy import validate_personal_averaging
from app.schemas.chart import ChartAnalysis, ZoneOut


def _daily(is_bullish: bool):
    if is_bullish:
        return [Candle(time="d0", open=1.0, high=1.02, low=0.99, close=1.015)]
    return [Candle(time="d0", open=1.015, high=1.02, low=0.99, close=1.0)]


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
    # Bearish OB spans 1.20-1.22; near the end (top half, "end" for a
    # sell approached from below) is 1.217.
    m15 = _smc(current_price=1.217, order_blocks=[_ob("bearish", 1.20, 1.22)])
    return validate_personal_averaging(_daily(False), m15)


def _add_on_validation() -> dict:
    m15 = _smc(current_price=1.103, order_blocks=[_ob("bullish", 1.10, 1.12)])
    return validate_personal_averaging(_daily(True), m15, open_trade_in_loss=True)


def _wait_validation() -> dict:
    return validate_personal_averaging([], None)  # no daily candle at all -> Daily Bias fails immediately


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
    assert "Daily Bias" in joined
    assert "M15 Order Block/FVG" in joined
    assert "Entry Timing" in joined


def test_add_on_signal_gets_its_own_headline_and_recommendation():
    validation = _add_on_validation()
    result = explain(_analysis(), validation)
    assert result["headline"] == "ADD-ON BUY"
    assert result["recommendation"] == "ADD"
    joined = " ".join(result["explanation"])
    assert "add-on" in joined.lower()


def test_wait_result_gets_wait_headline_and_names_the_failed_rule():
    validation = _wait_validation()
    result = explain(_analysis(), validation)
    assert result["headline"] == "WAIT"
    assert result["recommendation"] == "WAIT"
    joined = " ".join(result["explanation"])
    assert "Daily Bias" in joined


def test_confidence_breakdown_mirrors_the_strategys_own_rule_checks():
    validation = _valid_sell_validation()
    result = explain(_analysis(), validation)
    breakdown = result["confidence"]
    for key in ("daily_bias", "m15_poi", "entry_timing", "add_on", "overall"):
        assert 0 <= breakdown[key] <= 100, f"{key} out of range: {breakdown[key]}"
    assert breakdown["overall"] == validation["confidence"]


def test_confidence_breakdown_is_all_zero_when_first_rule_fails():
    validation = _wait_validation()
    result = explain(_analysis(), validation)
    breakdown = result["confidence"]
    assert breakdown["daily_bias"] == 0
    assert breakdown["m15_poi"] == 0
    assert breakdown["entry_timing"] == 0
    assert breakdown["add_on"] == 0
    assert breakdown["overall"] == 0


def test_valid_trade_scores_higher_overall_than_a_wait():
    valid_result = explain(_analysis(), _valid_sell_validation())
    wait_result = explain(_analysis(), _wait_validation())
    assert valid_result["confidence"]["overall"] > wait_result["confidence"]["overall"]


def test_break_even_price_is_narrated_when_present():
    validation = dict(_valid_sell_validation())
    validation["breakEvenPrice"] = 1.21234
    result = explain(_analysis(), validation)
    joined = " ".join(result["explanation"])
    assert "1.21234" in joined
