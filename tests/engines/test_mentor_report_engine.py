"""Mentor Report Engine tests (Sprint 20 Phase 7 -- periodic "AI Trade
Mentor" report). Confirms honest degradation per-field and that the
"most money" ranking is genuinely dollar-based, not win-rate-based.
"""
from app.engines.mentor_report_engine import MENTOR_REPORT_MIN_SAMPLE, build_mentor_report


def _trade(id_, pnl, **kw):
    base = {"id": id_, "pnl": pnl, "pair": "eurusd", "session": "London"}
    base.update(kw)
    return base


def test_no_data_below_minimum_sample():
    result = build_mentor_report([_trade("t1", 10), _trade("t2", -5)], [], [])
    assert result["hasEnoughData"] is False
    assert result["biggestImprovement"] is None
    assert result["bestSetup"] is None


def test_biggest_improvement_reflects_win_rate_delta():
    period = [_trade(f"p{i}", 10 if i < 3 else -10) for i in range(4)]  # 75% win rate
    previous = [_trade(f"q{i}", 10 if i < 1 else -10) for i in range(4)]  # 25% win rate
    result = build_mentor_report(period, previous, period + previous)
    assert result["biggestImprovement"] is not None
    assert "improved" in result["biggestImprovement"]
    assert "75%" in result["biggestImprovement"]
    assert "25%" in result["biggestImprovement"]


def test_biggest_improvement_none_without_prior_period_data():
    period = [_trade(f"p{i}", 10) for i in range(4)]
    result = build_mentor_report(period, [], period)
    assert result["biggestImprovement"] is None


def test_best_and_worst_setup_ranked_by_raw_money_not_win_rate():
    """A setup with a LOWER win rate but a bigger total dollar swing
    should still be able to win 'most money' -- confirms this ranks by
    totalPnl, a genuinely different question than the win-rate+
    expectancy rankScore group_stats normally sorts by."""
    high_winrate_low_money = [_trade(f"a{i}", 1.0, h4PoiType="Small Wins") for i in range(4)]  # 100% WR, $4 total
    lower_winrate_big_money = [
        _trade("b0", 500.0, h4PoiType="Big Money"),
        _trade("b1", 500.0, h4PoiType="Big Money"),
        _trade("b2", -50.0, h4PoiType="Big Money"),
    ]  # 66% WR but $950 total
    period = high_winrate_low_money + lower_winrate_big_money
    result = build_mentor_report(period, [], period)
    assert "Big Money" in result["bestSetup"]
    assert "Small Wins" in result["worstSetup"]


def test_costliest_habit_and_repeated_mistake_from_analyze_mistakes():
    period = [
        _trade(f"m{i}", -20.0, failedTags=["FOMO entry"]) for i in range(3)
    ] + [_trade("m3", -5.0, failedTags=["FOMO entry"])]
    result = build_mentor_report(period, [], period)
    assert "FOMO entry" in result["biggestRepeatedMistake"]
    assert "FOMO entry" in result["costliestHabit"]


def test_pair_to_stop_trading_requires_negative_expectancy():
    good_pair = [_trade(f"g{i}", 20, pair="eurusd") for i in range(4)]
    bad_pair = [_trade(f"b{i}", -20, pair="gbpjpy") for i in range(4)]
    result = build_mentor_report(good_pair + bad_pair, [], good_pair + bad_pair)
    assert result["bestPair"] is not None
    assert "EURUSD" in result["bestPair"]
    assert result["pairToStopTrading"] is not None
    assert "GBPJPY" in result["pairToStopTrading"]


def test_winner_and_loser_characteristic_use_full_history_not_just_period():
    winners = [_trade(f"w{i}", 30, session="London") for i in range(6)]
    losers = [_trade(f"l{i}", -30, session="Asian") for i in range(6)]
    full_history = winners + losers
    tiny_period = [_trade("only-one", 10, session="London")]
    result = build_mentor_report(tiny_period, [], full_history)
    assert result["winnerCharacteristic"] is not None
    assert "London" in result["winnerCharacteristic"]
    assert result["loserCharacteristic"] is not None
    assert "Asian" in result["loserCharacteristic"]


def test_never_contains_a_verdict_field():
    period = [_trade(f"t{i}", 10) for i in range(4)]
    result = build_mentor_report(period, [], period)
    forbidden = {"tradeStatus", "recommendation", "verdict", "isValid", "shouldTake"}
    assert forbidden.isdisjoint(result.keys())


def test_constant_matches_documented_honesty_bar():
    assert MENTOR_REPORT_MIN_SAMPLE == 3
