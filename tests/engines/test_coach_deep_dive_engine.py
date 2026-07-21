"""Coach Deep Dive Engine tests — Sprint 8 Phase 6.

``build_deep_dive()`` re-packages Sprint 6's setup/mistake/health engine
outputs; these tests construct those outputs directly (matching the
exact shapes ``group_stats()``/``analyze_mistakes()``/
``compute_strategy_health()`` actually produce) rather than re-deriving
statistics, so a regression here means the re-packaging logic broke,
not the underlying stats.
"""
from app.engines.coach_deep_dive_engine import (
    MIN_SAMPLE_FOR_WARNING,
    _why_losing,
    _why_winning,
    _worst_confident_row,
    _worst_session_for_pair,
    build_deep_dive,
)


def _row(key, count, win_rate, expectancy, rank_score, confident=True):
    return {
        "key": key,
        "count": count,
        "wins": max(0, count - 1),
        "losses": 1,
        "breakeven": 0,
        "winRate": win_rate,
        "expectancy": expectancy,
        "totalPnl": expectancy * count,
        "averageRR": None,
        "confident": confident,
        "rankScore": rank_score,
    }


# --- _worst_confident_row ------------------------------------------------------

def test_worst_confident_row_picks_lowest_rank_score_among_confident():
    rows = [_row("A", 5, 80, 50, 60), _row("B", 4, 20, -30, -20), _row("C", 1, 0, -100, -100, confident=False)]
    worst = _worst_confident_row(rows)
    assert worst["key"] == "B"  # C is excluded (not confident) despite the lowest raw rankScore


def test_worst_confident_row_none_when_no_confident_rows():
    rows = [_row("A", 1, 0, -100, -100, confident=False)]
    assert _worst_confident_row(rows) is None


def test_worst_confident_row_none_for_empty_or_missing():
    assert _worst_confident_row([]) is None
    assert _worst_confident_row(None) is None


# --- _why_losing / _why_winning -------------------------------------------------

def test_why_losing_mentions_harmful_habit_and_weakest_health():
    mistakes = {
        "mostHarmfulHabit": {"name": "FOMO", "count": 5, "pnl": -640.27, "totalLoss": 640.27},
        "mostExpensiveMistake": {"name": "Revenge Trading", "count": 3, "pnl": -300.0, "totalLoss": 300.0},
    }
    weakest_health = {"label": "Psychology", "percentage": 18, "grade": "F"}
    text = _why_losing(mistakes, weakest_health)
    assert "FOMO" in text and "640.27" in text
    assert "Revenge Trading" in text
    assert "Psychology" in text and "18%" in text and "F" in text


def test_why_losing_falls_back_when_no_data():
    assert "Not enough data" in _why_losing({}, None)


def test_why_winning_mentions_profitable_habit_and_best_setup():
    mistakes = {"mostProfitableHabit": {"name": "Patience", "count": 22, "pnl": 500.0, "winRate": 100.0}}
    best_setup_row = _row("Liquidity", 16, 62.5, 62.88, 40.0)
    text = _why_winning(mistakes, best_setup_row)
    assert "Patience" in text and "100%" in text
    assert "Liquidity" in text and "62%" in text


def test_why_winning_falls_back_when_no_data():
    assert "Not enough data" in _why_winning({}, None)


# --- build_deep_dive (full composition) -----------------------------------------

def _full_setups():
    return {
        "byDimension": {
            "day": [_row("Thursday", 6, 33.3, -61.3, -10), _row("Monday", 8, 70, 40, 30)],
            "pair": [_row("EURUSD", 12, 60, 20, 15), _row("XAUUSD", 8, 25, -23.2, -30)],
            "poi": [_row("Liquidity", 16, 62.5, 62.9, 40), _row("FVG", 11, 45.5, -11.7, -5)],
            "confirmation": [],
            "session": [_row("New York", 11, 72.7, 68.7, 50)],
        },
        "top": {
            "day": _row("Monday", 8, 70, 40, 30),
            "pair": _row("EURUSD", 12, 60, 20, 15),
            "poi": _row("Liquidity", 16, 62.5, 62.9, 40),
            "confirmation": None,
            "session": _row("New York", 11, 72.7, 68.7, 50),
        },
        "sampleSize": 40,
    }


def _full_mistakes():
    return {
        "mostHarmfulHabit": {"name": "FOMO", "count": 5, "pnl": -640.27, "totalLoss": 640.27},
        "mostExpensiveMistake": {"name": "FOMO", "count": 5, "pnl": -640.27, "totalLoss": 640.27},
        "mostProfitableHabit": {"name": "Patience", "count": 22, "pnl": 500.0, "winRate": 100.0},
    }


def _full_health():
    return {"components": [{"label": "Psychology", "percentage": 18, "grade": "F"}, {"label": "Discipline", "percentage": 70, "grade": "C"}]}


def test_build_deep_dive_full_data_populates_every_field():
    result = build_deep_dive(statistics={}, mistakes=_full_mistakes(), setups=_full_setups(), health=_full_health())

    assert "FOMO" in result["whyLosing"]
    assert "Patience" in result["whyWinning"]
    assert result["biggestMistake"]["name"] == "FOMO"
    assert result["bestSetup"]["key"] == "Liquidity"
    assert result["worstSetup"]["key"] == "FVG"
    assert result["worstDayToTrade"]["key"] == "Thursday"
    assert result["bestSession"]["key"] == "New York"
    # XAUUSD has negative expectancy and count >= MIN_SAMPLE_FOR_WARNING -> flagged
    assert result["pairToStopTrading"]["key"] == "XAUUSD"
    assert result["sampleSize"] == 40
    assert result["version"] == "8.0"


def test_build_deep_dive_no_pair_warning_when_expectancy_positive():
    setups = _full_setups()
    setups["byDimension"]["pair"] = [_row("EURUSD", 12, 60, 20, 15)]  # only a good pair, no bad one
    result = build_deep_dive(statistics={}, mistakes=_full_mistakes(), setups=setups, health=_full_health())
    assert result["pairToStopTrading"] is None


def test_build_deep_dive_no_pair_warning_below_sample_threshold():
    setups = _full_setups()
    setups["byDimension"]["pair"] = [_row("XAUUSD", MIN_SAMPLE_FOR_WARNING - 1, 25, -23.2, -30)]
    result = build_deep_dive(statistics={}, mistakes=_full_mistakes(), setups=setups, health=_full_health())
    assert result["pairToStopTrading"] is None


def test_build_deep_dive_handles_empty_history_gracefully():
    empty_setups = {"byDimension": {}, "top": {}, "sampleSize": 0}
    result = build_deep_dive(statistics={}, mistakes={}, setups=empty_setups, health={"components": []})

    assert "Not enough data" in result["whyLosing"]
    assert "Not enough data" in result["whyWinning"]
    assert result["biggestMistake"] is None
    assert result["bestSetup"] is None
    assert result["worstSetup"] is None
    assert result["worstDayToTrade"] is None
    assert result["bestSession"] is None
    assert result["pairToStopTrading"] is None
    assert result["sampleSize"] == 0


# --- _worst_session_for_pair (Sprint 22 follow-up) ------------------------------------------------------

def test_worst_session_for_pair_picks_session_with_most_losses():
    entries = [
        {"pair": "BTCUSD", "session": "London", "pnl": -10},
        {"pair": "BTCUSD", "session": "London", "pnl": -20},
        {"pair": "BTCUSD", "session": "New York", "pnl": -5},
        {"pair": "BTCUSD", "session": "New York", "pnl": 50},  # a win, doesn't count
        {"pair": "EURUSD", "session": "Asian", "pnl": -100},  # different pair, ignored
    ]
    assert _worst_session_for_pair(entries, "BTCUSD") == "London"


def test_worst_session_for_pair_none_when_no_losses():
    entries = [{"pair": "BTCUSD", "session": "London", "pnl": 40}]
    assert _worst_session_for_pair(entries, "BTCUSD") is None


def test_build_deep_dive_attaches_evidence_to_pair_to_stop_trading():
    """User-requested improvement: "Consider dropping: BTCUSD" alone
    isn't enough to decide on -- win rate and net P&L already came
    through the existing row (winRate/totalPnl), profitFactor now comes
    through group_stats() itself, and worstSession is computed here
    from the raw entries actually passed in."""
    setups = _full_setups()
    raw_entries = [
        {"pair": "XAUUSD", "session": "London", "pnl": -50},
        {"pair": "XAUUSD", "session": "London", "pnl": -30},
        {"pair": "XAUUSD", "session": "Asian", "pnl": -5},
        {"pair": "EURUSD", "session": "New York", "pnl": 100},
    ]
    result = build_deep_dive(
        statistics={}, mistakes=_full_mistakes(), setups=setups, health=_full_health(), entries=raw_entries
    )
    assert result["pairToStopTrading"]["key"] == "XAUUSD"
    assert result["pairToStopTrading"]["worstSession"] == "London"


def test_build_deep_dive_without_entries_still_works():
    """Backward compatible -- entries defaults to None/[] so existing
    callers that never pass it don't break; worstSession just stays
    None."""
    result = build_deep_dive(statistics={}, mistakes=_full_mistakes(), setups=_full_setups(), health=_full_health())
    assert result["pairToStopTrading"]["worstSession"] is None
