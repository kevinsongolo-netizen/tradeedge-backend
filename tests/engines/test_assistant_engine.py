"""Assistant Engine tests — Sprint 8 Phases 5 & 7.

Covers the individual scoring/classification helpers plus the full
``analyze_pretrade()`` composition, both with and without an available
ML result (the graceful-degradation path Phase 5 depends on).
"""
from app.engines.assistant_engine import (
    AVOID,
    BUY,
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    STRONG_BUY,
    WAIT,
    analyze_pretrade,
    classify_ai_confidence,
    classify_risk_level,
    compute_expected_rr,
    explain_trade,
    historical_reasons,
    recommend,
)


# --- classify_ai_confidence -------------------------------------------------

def test_confidence_low_without_ml():
    assert classify_ai_confidence(similar_trades_count=50, ml_available=False) == CONFIDENCE_LOW


def test_confidence_high_with_ml_and_lots_of_history():
    assert classify_ai_confidence(similar_trades_count=10, ml_available=True) == CONFIDENCE_HIGH


def test_confidence_medium_with_ml_and_some_history():
    assert classify_ai_confidence(similar_trades_count=5, ml_available=True) == CONFIDENCE_MEDIUM


def test_confidence_low_with_ml_but_thin_history():
    assert classify_ai_confidence(similar_trades_count=1, ml_available=True) == CONFIDENCE_LOW


# --- classify_risk_level -----------------------------------------------------

def test_risk_medium_when_no_planned_rr():
    assert classify_risk_level(planned_rr=None, historical_win_rate=70) == RISK_MEDIUM


def test_risk_high_for_low_rr():
    assert classify_risk_level(planned_rr=1.0, historical_win_rate=80) == RISK_HIGH


def test_risk_high_for_mid_rr_with_poor_history():
    assert classify_risk_level(planned_rr=2.0, historical_win_rate=30) == RISK_HIGH


def test_risk_medium_for_mid_rr_with_decent_history():
    assert classify_risk_level(planned_rr=2.0, historical_win_rate=60) == RISK_MEDIUM


def test_risk_low_for_high_rr_and_good_history():
    assert classify_risk_level(planned_rr=3.0, historical_win_rate=50) == RISK_LOW


def test_risk_medium_for_high_rr_but_poor_history():
    assert classify_risk_level(planned_rr=3.0, historical_win_rate=20) == RISK_MEDIUM


# --- compute_expected_rr -----------------------------------------------------

def test_expected_rr_none_when_inputs_missing():
    assert compute_expected_rr(win_probability=None, planned_rr=2.0) is None
    assert compute_expected_rr(win_probability=0.6, planned_rr=None) is None


def test_expected_rr_positive_expectancy():
    # 60% win at 2R: 0.6*2 - 0.4*1 = 0.8
    assert compute_expected_rr(win_probability=0.6, planned_rr=2.0) == 0.8


def test_expected_rr_negative_expectancy():
    # 20% win at 1.5R: 0.2*1.5 - 0.8*1 = -0.5
    assert compute_expected_rr(win_probability=0.2, planned_rr=1.5) == -0.5


# --- recommend ----------------------------------------------------------------

def test_recommend_wait_when_no_quality_score():
    assert recommend(quality_score=None, ai_confidence=CONFIDENCE_HIGH) == WAIT


def test_recommend_never_strong_buy_at_low_confidence():
    # Even a perfect quality score can't earn "Strong Buy" without real backing history.
    assert recommend(quality_score=95, ai_confidence=CONFIDENCE_LOW) == BUY


def test_recommend_avoid_at_low_confidence_and_low_score():
    assert recommend(quality_score=10, ai_confidence=CONFIDENCE_LOW) == AVOID


def test_recommend_strong_buy_at_high_confidence_and_high_score():
    assert recommend(quality_score=85, ai_confidence=CONFIDENCE_HIGH) == STRONG_BUY


def test_recommend_full_ladder_at_high_confidence():
    assert recommend(quality_score=65, ai_confidence=CONFIDENCE_HIGH) == BUY
    assert recommend(quality_score=45, ai_confidence=CONFIDENCE_HIGH) == WAIT
    assert recommend(quality_score=20, ai_confidence=CONFIDENCE_HIGH) == AVOID


# --- explain_trade (Phase 7) --------------------------------------------------

def test_explain_trade_all_strengths_for_fully_aligned_setup():
    candidate = {
        "direction": "buy",
        "h4_trend": "Bullish",
        "has_bos": True,
        "has_choch": True,
        "has_liquidity_sweep": True,
        "h4_poi_type": "Order Block",
        "planned_rr": 3.0,
        "confidence": 90,
        "session": "London",
    }
    result = explain_trade(candidate)
    assert any("aligns with the H4" in s for s in result["strengths"])
    assert any("BOS" in s for s in result["strengths"])
    assert any("CHOCH" in s for s in result["strengths"])
    assert any("Liquidity sweep" in s for s in result["strengths"])
    assert any("Order Block" in s for s in result["strengths"])
    assert any("High stated confidence" in s for s in result["strengths"])
    assert result["weaknesses"] == []


def test_explain_trade_flags_counter_trend_and_missing_confirmations():
    candidate = {
        "direction": "sell",
        "h4_trend": "Bullish",
        "has_bos": False,
        "has_choch": False,
        "has_liquidity_sweep": False,
        "planned_rr": 1.0,
        "confidence": 20,
    }
    result = explain_trade(candidate)
    assert any("counter to the H4" in w for w in result["weaknesses"])
    assert any("No BOS" in w for w in result["weaknesses"])
    assert any("No liquidity sweep" in w for w in result["weaknesses"])
    assert any("low" in w.lower() for w in result["weaknesses"])
    assert any("Low stated confidence" in w for w in result["weaknesses"])


def test_explain_trade_planned_rr_vs_historical_average():
    below = explain_trade({"planned_rr": 1.0}, historical_avg_rr=2.0)
    assert any("below your historical average" in w for w in below["weaknesses"])

    above = explain_trade({"planned_rr": 2.5}, historical_avg_rr=2.0)
    assert any("meets or exceeds" in s for s in above["strengths"])


def test_explain_trade_missing_h4_trend_is_a_weakness():
    result = explain_trade({"direction": "buy"})
    assert any("No H4 trend recorded" in w for w in result["weaknesses"])


# --- historical_reasons (Phase 7) ---------------------------------------------

def test_historical_reasons_no_similar_trades():
    reasons = historical_reasons(similar_trades_count=0, similar_win_rate=None, ml_available=True)
    assert any("No similar past trades" in r for r in reasons)


def test_historical_reasons_reports_win_rate():
    reasons = historical_reasons(similar_trades_count=8, similar_win_rate=62.5, ml_available=True)
    assert any("8 similar past trades" in r and "62%" in r for r in reasons)


def test_historical_reasons_notes_missing_model():
    reasons = historical_reasons(similar_trades_count=0, similar_win_rate=None, ml_available=False)
    assert any("No trained ML model yet" in r for r in reasons)


# --- analyze_pretrade (full composition) --------------------------------------

def test_analyze_pretrade_without_ml_falls_back_to_rule_score():
    candidate = {
        "direction": "buy",
        "h4_trend": "Bullish",
        "has_bos": True,
        "has_choch": True,
        "has_liquidity_sweep": True,
        "h4_poi_type": "Order Block",
        "planned_rr": 3.0,
        "confidence": 85,
        "rule_score": 90,
    }
    similar_result = {"similar": [], "winRate": None, "averageRR": None}
    result = analyze_pretrade(candidate, ml_result=None, similar_result=similar_result)

    assert result["ml_available"] is False
    assert result["trade_quality_score"] == 90
    assert result["win_probability"] is None
    assert result["ai_confidence"] == CONFIDENCE_LOW
    assert result["model_version"] is None
    assert result["algorithm"] is None
    assert any("No trained ML model yet" in r for r in result["historical_reasons"])
    # Phase 7 fields always present, even in the degraded path:
    assert isinstance(result["strengths"], list) and len(result["strengths"]) > 0
    assert isinstance(result["weaknesses"], list)


def test_analyze_pretrade_with_ml_and_similar_history():
    candidate = {
        "direction": "buy",
        "h4_trend": "Bullish",
        "has_bos": True,
        "has_choch": False,
        "has_liquidity_sweep": True,
        "planned_rr": 2.5,
        "confidence": 75,
        "rule_score": 70,
    }
    ml_result = {
        "winProbability": 0.62,
        "predictedQualityScore": 78.0,
        "modelVersion": "v3",
        "algorithm": "RandomForest",
    }
    similar_result = {
        "similar": [{"id": f"s{i}"} for i in range(12)],
        "winRate": 66.0,
        "averageRR": 2.0,
    }
    result = analyze_pretrade(candidate, ml_result=ml_result, similar_result=similar_result)

    assert result["ml_available"] is True
    assert result["trade_quality_score"] == 78.0
    assert result["win_probability"] == 0.62
    assert result["similar_trades_count"] == 12
    assert result["historical_win_rate"] == 66.0
    assert result["ai_confidence"] == CONFIDENCE_HIGH  # 12 similar trades + ml available
    assert result["model_version"] == "v3"
    assert result["algorithm"] == "RandomForest"
    assert result["expected_rr"] == compute_expected_rr(win_probability=0.62, planned_rr=2.5)
    assert result["recommendation"] in (STRONG_BUY, BUY, WAIT, AVOID)
