"""Mistake Engine tests."""
from app.engines.mistake_engine import analyze_mistakes


def test_detects_most_expensive_failed_tag():
    entries = [
        {"failedTags": ["FOMO"], "pnl": -100},
        {"failedTags": ["FOMO"], "pnl": -50},
        {"failedTags": ["Overtrading"], "pnl": -10},
    ]
    result = analyze_mistakes(entries)
    assert result["mostExpensiveMistake"]["name"] == "FOMO"


def test_profitable_and_harmful_habits_detected():
    entries = [
        {"workedTags": ["Patience"], "pnl": 100},
        {"workedTags": ["Patience"], "pnl": 100},
        {"failedTags": ["Revenge"], "pnl": -200},
    ]
    result = analyze_mistakes(entries)
    assert result["mostProfitableHabit"]["name"] == "Patience"
    assert result["mostHarmfulHabit"]["name"] == "Revenge"


def test_empty_entries_do_not_crash():
    result = analyze_mistakes([])
    assert result["mostCommonMistake"] is None
    assert result["topMistakes"] == []


def test_lost_profit_never_negative():
    entries = [{"emotion": "FOMO", "pnl": -30} for _ in range(3)] + [{"pnl": 40} for _ in range(3)]
    result = analyze_mistakes(entries)
    assert all(v >= 0 for v in result["lostProfit"].values())


def test_harmful_habit_is_none_when_the_only_tagged_trade_has_no_net_loss():
    """User-reported bug: a single trade tagged 'Chased price' that
    broke even (pnl exactly 0) was reported as 'linked to $0.00 in
    losses' / 'cost $0.00 across 1 trade' -- nonsensical, since nothing
    was actually lost. A habit tag only counts as the 'most harmful'
    once it has a real net loss to point to."""
    entries = [{"failedTags": ["Chased price"], "pnl": 0.0}]
    result = analyze_mistakes(entries)
    assert result["mostHarmfulHabit"] is None
    assert result["mostExpensiveMistake"] is None


def test_harmful_habit_ignores_a_winning_tagged_trade():
    entries = [{"failedTags": ["Chased price"], "pnl": 25.0}]
    result = analyze_mistakes(entries)
    assert result["mostHarmfulHabit"] is None


def test_harmful_habit_still_detected_among_a_mix_of_tags():
    entries = [
        {"failedTags": ["Chased price"], "pnl": 25.0},
        {"failedTags": ["Revenge trade"], "pnl": -60.0},
    ]
    result = analyze_mistakes(entries)
    assert result["mostHarmfulHabit"]["name"] == "Revenge trade"
    assert result["mostHarmfulHabit"]["totalLoss"] == 60.0
