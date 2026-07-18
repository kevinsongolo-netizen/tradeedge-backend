"""Trade Lesson Engine tests (Sprint 20 Phase 2 #4 -- planned-vs-actual).

Every lesson must be traceable to a number already in the journal
(stop distance %, target distance %, win rate of similar setups) --
these tests pin down the honest-degradation path (too little history),
the stop/target sizing comparisons, and the win/loss pattern notes.
"""
from __future__ import annotations

import pytest

from app.engines.trade_lesson_engine import build_trade_lesson


def _trade(**overrides):
    base = {
        "id": "candidate-1",
        "pair": "EURUSD",
        "direction": "buy",
        "asset": "Forex",
        "entry": 1.1000,
        "exit": 1.1050,
        "sl": 1.0950,
        "tp": 1.1150,
        "lots": 0.1,
        "pnl": 50.0,
        "rr": 3.0,
        "h4Trend": "Bullish",
        "h4PoiType": "FVG",
        "session": "New York",
    }
    base.update(overrides)
    return base


def _similar_history_row(i, *, outcome_pnl, sl_pct, tp_pct, entry=1.1000):
    """Builds a history row similar enough to `_trade()`'s candidate
    (same pair/direction/asset/h4Trend/h4PoiType/session) so it clears
    search_similar's default threshold, with a stop/target sized at an
    exact % of entry for precise test assertions."""
    return {
        "id": f"hist-{i}",
        "pair": "EURUSD",
        "direction": "buy",
        "asset": "Forex",
        "entry": entry,
        "sl": entry * (1 - sl_pct / 100),
        "tp": entry * (1 + tp_pct / 100),
        "lots": 0.1,
        "pnl": outcome_pnl,
        "rr": 2.0,
        "h4Trend": "Bullish",
        "h4PoiType": "FVG",
        "session": "New York",
    }


def test_raises_if_trade_has_no_exit_yet():
    trade = _trade()
    del trade["exit"]
    trade["exit"] = None
    with pytest.raises(ValueError, match="doesn't have an exit price yet"):
        build_trade_lesson(trade, [])


def test_too_little_history_degrades_honestly_instead_of_guessing():
    history = [_similar_history_row(i, outcome_pnl=10, sl_pct=0.5, tp_pct=1.5) for i in range(2)]
    result = build_trade_lesson(_trade(), history)
    assert result["hasEnoughHistory"] is False
    assert result["sampleSize"] < 3
    assert "Not enough similar closed trades" in result["lessons"][0]
    assert result["patterns"] == []


def test_tighter_stop_than_winners_is_flagged():
    # Candidate's stop is 0.1000/1.1000 = ~0.45% away; winners' stops are
    # sized at 2% -- well under the 0.7x ratio, so this should trigger
    # the "tighter than your winners" lesson.
    trade = _trade(entry=1.1000, sl=1.0950, tp=1.1500)  # stop ~0.45%, target ~4.5%
    history = [_similar_history_row(i, outcome_pnl=10, sl_pct=2.0, tp_pct=4.5) for i in range(5)]
    result = build_trade_lesson(trade, history)
    assert result["hasEnoughHistory"] is True
    joined = " ".join(result["lessons"])
    assert "tighter than your average winning trade" in joined


def test_wider_stop_than_winners_is_flagged():
    trade = _trade(entry=1.1000, sl=1.0500, tp=1.1500)  # stop ~4.5%, target ~4.5%
    history = [_similar_history_row(i, outcome_pnl=10, sl_pct=1.0, tp_pct=4.5) for i in range(5)]
    result = build_trade_lesson(trade, history)
    joined = " ".join(result["lessons"])
    assert "wider than your average winning trade" in joined


def test_ambitious_target_vs_winners_is_flagged():
    trade = _trade(entry=1.1000, sl=1.0900, tp=1.2000)  # stop ~0.9%, target ~9%
    history = [_similar_history_row(i, outcome_pnl=10, sl_pct=0.9, tp_pct=3.0) for i in range(5)]
    result = build_trade_lesson(trade, history)
    joined = " ".join(result["lessons"])
    assert "more ambitious than what's typically worked" in joined


def test_no_sizing_difference_falls_back_to_reassurance_lesson():
    trade = _trade(entry=1.1000, sl=1.0900, tp=1.1300)  # stop ~0.9%, target ~2.7%
    history = [_similar_history_row(i, outcome_pnl=10, sl_pct=0.9, tp_pct=2.7) for i in range(5)]
    result = build_trade_lesson(trade, history)
    joined = " ".join(result["lessons"])
    assert "in line with what's worked before" in joined


def test_loss_with_historically_strong_setup_notes_good_setup_bad_luck():
    trade = _trade(pnl=-40, sl=1.0900, tp=1.1300)
    history = (
        [_similar_history_row(i, outcome_pnl=10, sl_pct=0.9, tp_pct=2.7) for i in range(4)]
        + [_similar_history_row(i + 10, outcome_pnl=-10, sl_pct=0.9, tp_pct=2.7) for i in range(1)]
    )
    result = build_trade_lesson(trade, history)
    assert result["outcome"] == "Loss"
    assert result["wins"] == 4
    assert result["losses"] == 1
    joined = " ".join(result["patterns"])
    assert "didn't play out this time, not a flawed one" in joined


def test_loss_with_historically_weak_setup_notes_pattern_not_bad_luck():
    trade = _trade(pnl=-40, sl=1.0900, tp=1.1300)
    history = (
        [_similar_history_row(i, outcome_pnl=-10, sl_pct=0.9, tp_pct=2.7) for i in range(4)]
        + [_similar_history_row(i + 10, outcome_pnl=10, sl_pct=0.9, tp_pct=2.7) for i in range(1)]
    )
    result = build_trade_lesson(trade, history)
    assert result["losses"] == 4
    assert result["wins"] == 1
    joined = " ".join(result["patterns"])
    assert "hasn't been working for you" in joined


def test_win_with_historically_mixed_setup_notes_caution():
    trade = _trade(pnl=40, sl=1.0900, tp=1.1300)
    history = (
        [_similar_history_row(i, outcome_pnl=10, sl_pct=0.9, tp_pct=2.7) for i in range(3)]
        + [_similar_history_row(i + 10, outcome_pnl=-10, sl_pct=0.9, tp_pct=2.7) for i in range(2)]
    )
    result = build_trade_lesson(trade, history)
    assert result["outcome"] == "Win"
    joined = " ".join(result["patterns"])
    assert "also lost" in joined


def test_output_never_contains_a_verdict_field():
    trade = _trade()
    history = [_similar_history_row(i, outcome_pnl=10, sl_pct=0.9, tp_pct=2.7) for i in range(5)]
    result = build_trade_lesson(trade, history)
    for banned in ("tradeStatus", "recommendation", "verdict", "shouldTake"):
        assert banned not in result
