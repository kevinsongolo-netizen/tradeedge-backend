"""Unit tests for Level 3 (app/chart/coach_explainer.py)."""
from app.chart.coach_explainer import explain
from app.chart.trade_validator import validate_trade
from app.schemas.chart import ChartAnalysis, ZoneOut


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


def test_valid_trade_gets_buy_headline_and_never_just_says_buy():
    analysis = _analysis()
    validation = validate_trade(analysis, planned_rr=3.0)
    result = explain(analysis, validation)
    assert result["headline"] == "BUY ANALYSIS"
    assert result["recommendation"] == "BUY"
    # Spec requirement: always explain WHY, multiple sentences, not just "Buy".
    assert len(result["explanation"]) >= 3
    assert all(isinstance(s, str) and s for s in result["explanation"])


def test_invalid_trade_gets_no_trade_headline_and_wait_recommendation():
    analysis = _analysis(trend="Bearish", structure="Bearish")  # against BUY bias -> invalid
    validation = validate_trade(analysis, planned_rr=3.0)
    result = explain(analysis, validation)
    assert result["headline"] == "NO TRADE"
    assert result["recommendation"] == "WAIT"
    assert "Wait for confirmation." in result["explanation"]


def test_confidence_breakdown_fields_all_in_0_100_range():
    analysis = _analysis()
    validation = validate_trade(analysis, planned_rr=3.0)
    result = explain(analysis, validation)
    breakdown = result["confidence"]
    for key in ("trendAlignment", "poiQuality", "liquidityQuality", "bosQuality", "chochQuality", "fvgQuality", "rrQuality", "overall"):
        assert 0 <= breakdown[key] <= 100, f"{key} out of range: {breakdown[key]}"


def test_aligned_trend_scores_higher_than_misaligned():
    good = _analysis()
    good_validation = validate_trade(good, planned_rr=3.0)
    good_result = explain(good, good_validation)

    bad = _analysis(trend="Bearish", structure="Bearish")
    bad_validation = validate_trade(bad, planned_rr=3.0)
    bad_result = explain(bad, bad_validation)

    assert good_result["confidence"]["trendAlignment"] > bad_result["confidence"]["trendAlignment"]
    assert good_result["confidence"]["overall"] > bad_result["confidence"]["overall"]
