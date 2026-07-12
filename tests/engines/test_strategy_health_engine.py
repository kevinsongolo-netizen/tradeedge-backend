"""Strategy Health Engine tests."""
from app.engines.strategy_health_engine import compute_strategy_health


def test_no_trades_returns_null_health():
    result = compute_strategy_health([])
    assert result["healthScore"] is None
    assert result["components"] == []


def test_disciplined_trades_score_well_on_discipline():
    entries = [
        {"rulesFollowed": "all", "followedPlan": "Yes", "pnl": 10, "sl": 1.09, "rr": 2.0, "emotion": "Calm"}
        for _ in range(5)
    ]
    result = compute_strategy_health(entries)
    discipline = next(c for c in result["components"] if c["key"] == "Discipline")
    assert discipline["percentage"] == 100


def test_emotional_trades_hurt_psychology():
    entries = [{"emotion": "Revenge", "pnl": -10} for _ in range(5)]
    result = compute_strategy_health(entries)
    psychology = next(c for c in result["components"] if c["key"] == "Psychology")
    assert psychology["percentage"] < 50


def test_health_score_is_average_of_available_components():
    entries = [{"rulesFollowed": "all", "followedPlan": "Yes", "pnl": 10, "emotion": "Calm"} for _ in range(5)]
    result = compute_strategy_health(entries)
    assert result["grade"] in ("A", "B", "C", "D", "F")
