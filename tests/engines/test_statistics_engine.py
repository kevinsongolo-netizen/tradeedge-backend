"""Statistics Engine tests — win rate, profit factor, expectancy, streaks."""
from app.engines.statistics_engine import build_chart_data, compute_statistics, statistics_core

WINS_AND_LOSSES = [
    {"id": "1", "date": "2026-01-01", "pnl": 100, "rr": 2.0, "pair": "EURUSD", "session": "London"},
    {"id": "2", "date": "2026-01-02", "pnl": -50, "rr": 1.0, "pair": "EURUSD", "session": "London"},
    {"id": "3", "date": "2026-01-03", "pnl": 200, "rr": 3.0, "pair": "GBPUSD", "session": "Asian"},
    {"id": "4", "date": "2026-01-04", "pnl": 0, "rr": 1.5, "pair": "GBPUSD", "session": "Asian"},
]


def test_core_counts_and_rates():
    core = statistics_core(WINS_AND_LOSSES)
    assert core["totalTrades"] == 4
    assert core["wins"] == 2
    assert core["losses"] == 1
    assert core["breakeven"] == 1
    assert core["winRate"] == 50.0


def test_profit_factor_and_expectancy():
    core = statistics_core(WINS_AND_LOSSES)
    assert core["profitFactor"] == (300 / 50)
    assert core["expectancy"] == (250 / 4)


def test_empty_entries_do_not_crash():
    core = statistics_core([])
    assert core["totalTrades"] == 0
    assert core["profitFactor"] == 0
    assert core["winRate"] == 0


def test_all_wins_profit_factor_is_infinite():
    core = statistics_core([{"id": "1", "pnl": 100, "date": "2026-01-01"}])
    import math
    assert math.isinf(core["profitFactor"])


def test_streaks_detected_correctly():
    entries = [
        {"id": "1", "date": "2026-01-01", "pnl": 10},
        {"id": "2", "date": "2026-01-02", "pnl": 10},
        {"id": "3", "date": "2026-01-03", "pnl": -10},
        {"id": "4", "date": "2026-01-04", "pnl": 10},
        {"id": "5", "date": "2026-01-05", "pnl": 10},
        {"id": "6", "date": "2026-01-06", "pnl": 10},
    ]
    core = statistics_core(entries)
    assert core["consecutiveWins"] == 3
    assert core["currentWinningStreak"] == 3


def test_group_breakdowns_by_pair_and_session():
    stats = compute_statistics(WINS_AND_LOSSES)
    assert "EURUSD" in stats["byPair"]
    assert "GBPUSD" in stats["byPair"]
    assert stats["byPair"]["EURUSD"]["totalTrades"] == 2
    assert "London" in stats["bySession"]


def test_best_pair_and_session_are_populated():
    stats = compute_statistics(WINS_AND_LOSSES)
    assert stats["bestPair"] in ("EURUSD", "GBPUSD")
    assert stats["bestSession"] in ("London", "Asian")


def test_cache_returns_same_object_for_same_input():
    a = compute_statistics(WINS_AND_LOSSES)
    b = compute_statistics(WINS_AND_LOSSES)
    assert a is b  # fingerprint cache hit


def test_cache_invalidates_on_different_input():
    a = compute_statistics(WINS_AND_LOSSES)
    b = compute_statistics(WINS_AND_LOSSES[:2])
    assert a is not b
    assert b["totalTrades"] == 2


def test_chart_data_shape():
    charts = build_chart_data(WINS_AND_LOSSES)
    for key in ("ruleScoreTrend", "winRateTrend", "profitFactorTrend", "monthlyPerformance", "pairPerformance"):
        assert key in charts
    assert isinstance(charts["pairPerformance"], list)
