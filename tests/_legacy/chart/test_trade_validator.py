"""Unit tests for Level 2 (app/chart/trade_validator.py) — built against
hand-constructed ChartAnalysis instances so each rule can be tested in
isolation, independent of either Level-1 reading path."""
from app._legacy.chart.trade_validator import validate_trade
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


def test_valid_buy_trade_passes_all_rules():
    analysis = _analysis()
    result = validate_trade(analysis, planned_rr=3.0)
    assert result["tradeStatus"] == "VALID"
    assert result["direction"] == "buy"
    assert result["recommendation"] == "TAKE"
    assert not result["reasonsFailed"]
    assert any("H4 Bullish Trend" in r for r in result["reasonsPassed"])


def test_fails_when_against_higher_timeframe_trend():
    analysis = _analysis(trend="Bearish", structure="Bearish")  # bias still BUY
    result = validate_trade(analysis, planned_rr=3.0)
    assert result["tradeStatus"] == "INVALID"
    assert any("Against Higher Time Frame Trend" in r for r in result["reasonsFailed"])


def test_fails_when_rr_below_minimum():
    analysis = _analysis()
    result = validate_trade(analysis, planned_rr=1.2, min_rr=2.0)
    assert result["tradeStatus"] == "INVALID"
    assert any("RR below 1:2" in r for r in result["reasonsFailed"])
    assert result["recommendation"] == "WAIT"


def test_fails_when_no_direction_can_be_resolved():
    analysis = _analysis(bias="NONE")
    result = validate_trade(analysis)
    assert result["tradeStatus"] == "INVALID"
    assert result["direction"] is None
    assert result["confidence"] == 0


def test_fails_when_no_confirmation_available():
    analysis = _analysis(latestEvent=None)
    result = validate_trade(analysis, planned_rr=3.0)
    assert any("No Confirmation" in r for r in result["reasonsFailed"])


def test_suggests_entry_sl_tp_from_candle_sourced_zone():
    analysis = _analysis()
    result = validate_trade(analysis, planned_rr=3.0)
    assert result["suggestedEntry"] == 1.0925  # midpoint of the entry zone
    assert result["stopLoss"] < 1.0900  # below the zone for a buy
    assert result["takeProfit"] > result["suggestedEntry"]


def test_screenshot_sourced_analysis_has_no_numeric_suggestion():
    analysis = _analysis(source="screenshot", entryZone=None)
    result = validate_trade(analysis, planned_rr=3.0)
    assert result["suggestedEntry"] is None
    assert result["stopLoss"] is None
    assert result["takeProfit"] is None


def test_sell_direction_resolved_from_bearish_bias():
    analysis = _analysis(
        trend="Bearish",
        structure="Bearish",
        bias="SELL",
        premiumDiscount="Premium",
        entryZone=ZoneOut(kind="bearish", zoneType="Order Block", high=1.1050, low=1.1000, mitigated=False),
        currentPriceContext="Inside Bearish Order Block (1.10000-1.10500)",
    )
    result = validate_trade(analysis, planned_rr=2.5)
    assert result["direction"] == "sell"
    assert result["tradeStatus"] == "VALID"
    assert result["stopLoss"] > result["suggestedEntry"]  # stop above entry for a sell
