"""Tests for multi-timeframe confirmation (Sprint 12)."""
from app.chart.multi_timeframe import confirm_with_m15
from app.schemas.chart import ChartAnalysis


def _m15_analysis(**overrides):
    base = dict(
        source="candles",
        trend="Bullish",
        structure="Bullish",
        current_price_context="Inside Bullish Order Block",
        liquidity="No clear equal-highs/equal-lows liquidity detected",
        latest_event="Bullish BOS detected",
        fvg_status=None,
        premium_discount="Discount",
        bias="BUY",
        confidence=92,
        zones=[],
        entry_zone=None,
        notes=[],
        is_placeholder=False,
    )
    base.update(overrides)
    return ChartAnalysis(**base)


def test_bullish_bos_confirms_buy_direction():
    result = confirm_with_m15(_m15_analysis(), "buy")
    assert result["has_m15_bos"] is True
    assert result["aligned"] is True


def test_bearish_bos_does_not_confirm_buy_direction():
    m15 = _m15_analysis(latest_event="Bearish BOS detected", trend="Bearish", bias="SELL")
    result = confirm_with_m15(m15, "buy")
    assert result["has_m15_bos"] is False
    assert result["has_m15_entry_confirmation"] is False
    assert result["aligned"] is False


def test_choch_detected_correctly():
    m15 = _m15_analysis(latest_event="Bullish CHOCH detected")
    result = confirm_with_m15(m15, "buy")
    assert result["has_m15_choch"] is True


def test_trend_alignment_alone_confirms():
    m15 = _m15_analysis(latest_event=None, trend="Bullish")
    result = confirm_with_m15(m15, "buy")
    assert result["has_m15_entry_confirmation"] is True
    assert result["aligned"] is True


def test_sell_direction_with_bearish_bos():
    m15 = _m15_analysis(latest_event="Bearish BOS detected", trend="Bearish", bias="SELL")
    result = confirm_with_m15(m15, "sell")
    assert result["has_m15_bos"] is True
    assert result["aligned"] is True


def test_no_confirmation_notes_present():
    m15 = _m15_analysis(latest_event=None, trend="Ranging", bias="NONE")
    result = confirm_with_m15(m15, "buy")
    assert result["aligned"] is False
    assert any("does not yet confirm" in n for n in result["notes"])
