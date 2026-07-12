"""Execution Engine tests — discipline scoring, grading, score combination."""
from app.engines.execution_engine import combine_scores, compute_execution_score, score_band

CLEAN_TRADE = {
    "entry": 1.0850,
    "sl": 1.0820,
    "tp": 1.0920,
    "rr": 2.1,
    "exitReason": "Take Profit Hit",
    "emotion": "Calm",
    "notes": "Followed the plan exactly.",
    "date": "2026-01-01",
}


def test_clean_trade_scores_high_and_grades_excellent():
    result = compute_execution_score(CLEAN_TRADE, [])
    assert result["score"] >= 90
    assert result["grade"] == "EXCELLENT"
    assert result["mistakes"] == []


def test_emotional_exit_is_detected_as_mistake():
    trade = {**CLEAN_TRADE, "exitReason": "Manual Close - Fear/Uncertainty", "emotion": "FOMO"}
    result = compute_execution_score(trade, [])
    assert result["score"] < 90
    assert any("emotional" in m.lower() or "fomo" in m.lower() for m in result["mistakes"])


def test_overtrading_detected_from_same_day_history():
    trade = {**CLEAN_TRADE, "date": "2026-01-05"}
    history = [{"date": "2026-01-05"} for _ in range(4)]
    result = compute_execution_score(trade, history)
    overtrading_check = next(c for c in result["reasons"] if c["key"] == "overtrading")
    assert overtrading_check["ok"] is False


def test_incomplete_entry_plan_fails_entry_quality():
    trade = {"exitReason": "Take Profit Hit"}
    result = compute_execution_score(trade, [])
    entry_check = next(c for c in result["reasons"] if c["key"] == "entryQuality")
    assert entry_check["ok"] is False


def test_grade_bands():
    assert compute_execution_score(CLEAN_TRADE, [])["grade"] in ("EXCELLENT", "GOOD")
    # An empty trade fails entryQuality + followedExitPlan (no plan
    # recorded) but most "did you do X bad thing" checks default to
    # "no evidence of it" = pass, so the grade lands in FAIR, not POOR.
    # This mirrors the JS engine's design exactly.
    empty_result = compute_execution_score({}, [])
    assert empty_result["grade"] in ("FAIR", "POOR")
    assert empty_result["score"] < 90


def test_combine_scores_averages_both():
    assert combine_scores(80, 90) == 85
    assert combine_scores(80, None) == 80
    assert combine_scores(None, 90) == 90
    assert combine_scores(None, None) is None


def test_combine_scores_clamped_0_100():
    assert combine_scores(150, 150) == 100
    assert combine_scores(-50, -50) == 0


def test_score_band_labels():
    assert score_band(95)["label"] == "Excellent"
    assert score_band(85)["label"] == "Good"
    assert score_band(72)["label"] == "Fair"
    assert score_band(10)["label"] == "Poor"
    assert score_band(None)["label"] == "Unknown"


def test_revenge_and_fomo_text_detection():
    trade = {**CLEAN_TRADE, "notes": "This was a revenge trade after the last loss."}
    result = compute_execution_score(trade, [])
    revenge_check = next(c for c in result["reasons"] if c["key"] == "revengeTrading")
    assert revenge_check["ok"] is False
