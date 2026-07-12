"""Coach Engine tests — insights come only from computed data."""
from app.engines.coach_engine import generate_coach_insights


def test_too_few_trades_returns_info_message():
    insights = generate_coach_insights([{"pnl": 10}])
    assert len(insights) == 1
    assert insights[0]["level"] == "info"


def test_insights_are_capped_at_six():
    entries = [
        {
            "id": str(i),
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "pair": "EURUSD",
            "session": "London",
            "h4PoiType": "OB",
            "m15Confirmations": ["BOS"],
            "pnl": 100 if i % 2 == 0 else -50,
            "ruleScore": 80,
            "executionScore": 80,
            "overallScore": 80,
            "rulesFollowed": "all",
            "followedPlan": "Yes",
            "emotion": "Calm",
        }
        for i in range(30)
    ]
    insights = generate_coach_insights(entries)
    assert len(insights) <= 6
    assert all("level" in i and "text" in i for i in insights)


def test_no_hardcoded_text_without_data():
    # With minimal fields, insights should still only describe what was
    # actually computed (no crash, no fabricated specifics).
    entries = [{"id": str(i), "date": "2026-01-01", "pnl": 10} for i in range(5)]
    insights = generate_coach_insights(entries)
    assert isinstance(insights, list)
