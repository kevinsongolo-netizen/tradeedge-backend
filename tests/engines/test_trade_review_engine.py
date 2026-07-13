"""Tests for the AI review-after-close engine (Sprint 11)."""
import pytest

from app.engines.trade_review_engine import build_trade_review


def _base_trade(**overrides):
    trade = {
        "pair": "EURUSD",
        "direction": "buy",
        "entry": 1.1000,
        "exit": 1.1100,
        "pnl": 50.0,
        "rr": 2.5,
        "rulesFollowed": "all",
        "workedTags": ["Followed my plan"],
        "failedTags": [],
        "exitReason": "Take Profit Hit",
        "h4Trend": "Bullish",
        "h4PoiType": "Order Block",
    }
    trade.update(overrides)
    return trade


def test_missing_exit_raises():
    trade = _base_trade()
    del trade["exit"]
    with pytest.raises(ValueError, match="exit price"):
        build_trade_review(trade)


def test_clean_win_headline_and_no_negatives():
    result = build_trade_review(_base_trade())
    assert result["outcome"] == "WIN"
    assert result["headline"] == "WIN — Clean Execution"
    assert result["what_went_wrong"] == []
    assert "Risk:Reward was 2.5" in result["what_worked"][-1] or any(
        "2.5" in w for w in result["what_worked"]
    )


def test_loss_with_broken_rules():
    trade = _base_trade(
        pnl=-30.0,
        rulesFollowed="none",
        workedTags=[],
        failedTags=["Revenge trade", "No stop loss"],
        exitReason="Stop Loss Hit",
        rr=1.0,
    )
    result = build_trade_review(trade)
    assert result["outcome"] == "LOSS"
    assert result["headline"] == "LOSS — Rules Were Broken"
    assert "Revenge trade" in result["what_went_wrong"]
    assert "No stop loss" in result["what_went_wrong"]
    assert result["lesson"] == result["what_went_wrong"][0]


def test_pnl_inferred_when_missing():
    trade = _base_trade(direction="sell", entry=100.0, exit=95.0)
    del trade["pnl"]
    result = build_trade_review(trade)
    # sell: pnl = entry - exit = 5 > 0 -> WIN
    assert result["outcome"] == "WIN"


def test_missing_h4_trend_and_poi_flagged():
    trade = _base_trade(h4Trend=None, h4PoiType=None)
    result = build_trade_review(trade)
    assert any("H4 trend" in w for w in result["what_went_wrong"])
    assert any("POI" in w for w in result["what_went_wrong"])


def test_followed_plan_note_matches_rules_followed():
    trade = _base_trade(rulesFollowed="some")
    result = build_trade_review(trade)
    assert result["followed_plan_note"] == "You only partially followed your plan."


def test_breakeven_outcome():
    trade = _base_trade(pnl=0.0)
    result = build_trade_review(trade)
    assert result["outcome"] == "BREAKEVEN"
