"""Sprint 8 — Intelligent Trading Assistant engine (Vision Phases 5 & 7).

Pure functions only (no DB, no HTTP — same engine contract as every
other module in this package): turns an ML prediction (Sprint 7,
optional — the assistant still works, in a reduced form, before any
model has been trained) plus historical similar-trade context into a
single pre-trade recommendation with a plain-language explanation.

Phase 7 ("Explainable AI") isn't a second model bolted onto the first —
scikit-learn's RandomForest/GradientBoosting aren't trivially
explainable without something like SHAP (out of scope for v1, noted in
TODO.md). Instead, ``explain_trade()`` independently checks the same
setup fields a trader would check by eye (trend alignment, BOS/CHOCH,
liquidity sweep, planned RR vs. their own historical average, stated
confidence) and reports them as plain strengths/weaknesses — honest
about being rule-based/statistical, not a decomposition of the model's
internal weights.
"""
from __future__ import annotations

from typing import Any

ASSISTANT_ENGINE_VERSION = "8.0"

STRONG_BUY = "Strong Buy"
BUY = "Buy"
WAIT = "Wait"
AVOID = "Avoid"

RISK_LOW = "Low"
RISK_MEDIUM = "Medium"
RISK_HIGH = "High"

CONFIDENCE_HIGH = "High"
CONFIDENCE_MEDIUM = "Medium"
CONFIDENCE_LOW = "Low"


def classify_ai_confidence(*, similar_trades_count: int, ml_available: bool) -> str:
    """How much to trust this specific analysis — driven by how much
    relevant history backs it up, not by the win probability itself
    (a model can be very sure and still be wrong on thin data)."""
    if not ml_available:
        return CONFIDENCE_LOW
    if similar_trades_count >= 10:
        return CONFIDENCE_HIGH
    if similar_trades_count >= 3:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def classify_risk_level(*, planned_rr: float | None, historical_win_rate: float | None) -> str:
    """Risk level from the trade's own planned reward:risk, tempered by
    how this type of setup has actually performed historically (a 3R
    plan means less if similar past trades barely win half the time)."""
    if planned_rr is None:
        return RISK_MEDIUM
    if planned_rr < 1.5:
        return RISK_HIGH
    if planned_rr < 2.5:
        if historical_win_rate is not None and historical_win_rate < 40:
            return RISK_HIGH
        return RISK_MEDIUM
    if historical_win_rate is not None and historical_win_rate < 35:
        return RISK_MEDIUM
    return RISK_LOW


def compute_expected_rr(*, win_probability: float | None, planned_rr: float | None) -> float | None:
    """Expectancy in R-multiples: win_probability * reward - (1 -
    win_probability) * 1R risked. None if either input is missing —
    never silently substitutes a default that would look like a real
    number."""
    if win_probability is None or planned_rr is None:
        return None
    return round(win_probability * planned_rr - (1 - win_probability) * 1.0, 2)


def recommend(*, quality_score: float | None, ai_confidence: str) -> str:
    """Strong Buy / Buy / Wait / Avoid. Thresholds are deliberately
    conservative when ``ai_confidence`` is Low (thin history or no
    trained model yet) — a low-confidence analysis can suggest Buy or
    Avoid at the extremes but never Strong Buy, since "strong" implies
    real historical backing this analysis doesn't have yet."""
    if quality_score is None:
        return WAIT
    if ai_confidence == CONFIDENCE_LOW:
        if quality_score >= 80:
            return BUY
        if quality_score < 40:
            return AVOID
        return WAIT
    if quality_score >= 80:
        return STRONG_BUY
    if quality_score >= 60:
        return BUY
    if quality_score >= 40:
        return WAIT
    return AVOID


def explain_trade(candidate: dict[str, Any], *, historical_avg_rr: float | None = None) -> dict[str, list[str]]:
    """explain_trade(candidate, historical_avg_rr=None) — Phase 7.
    ``candidate`` uses the same field names as
    ``app/schemas/ml_training.py::PredictionRequest`` (snake_case:
    ``h4_trend``, ``has_bos``, ``planned_rr``, etc.)."""
    strengths: list[str] = []
    weaknesses: list[str] = []

    direction = candidate.get("direction")
    h4_trend = candidate.get("h4_trend")
    if direction and h4_trend:
        aligned = (direction == "buy" and h4_trend == "Bullish") or (direction == "sell" and h4_trend == "Bearish")
        if aligned:
            strengths.append(f"Trade direction aligns with the H4 {h4_trend} trend")
        else:
            weaknesses.append(f"Trade direction is counter to the H4 {h4_trend} trend")
    elif not h4_trend:
        weaknesses.append("No H4 trend recorded for this setup")

    if candidate.get("has_bos"):
        strengths.append("BOS (Break of Structure) confirmed")
    else:
        weaknesses.append("No BOS confirmation")

    if candidate.get("has_choch"):
        strengths.append("CHOCH (Change of Character) present")

    if candidate.get("has_liquidity_sweep"):
        strengths.append("Liquidity sweep present")
    else:
        weaknesses.append("No liquidity sweep")

    if candidate.get("h4_poi_type"):
        strengths.append(f"Clear POI: {candidate['h4_poi_type']}")

    planned_rr = candidate.get("planned_rr")
    if planned_rr is not None:
        if historical_avg_rr is not None:
            if planned_rr < historical_avg_rr - 0.3:
                weaknesses.append(
                    f"Planned RR ({planned_rr:.1f}) is below your historical average ({historical_avg_rr:.1f})"
                )
            else:
                strengths.append(
                    f"Planned RR ({planned_rr:.1f}) meets or exceeds your historical average ({historical_avg_rr:.1f})"
                )
        elif planned_rr < 1.5:
            weaknesses.append(f"Planned RR ({planned_rr:.1f}) is low")

    confidence = candidate.get("confidence")
    if confidence is not None:
        if confidence >= 70:
            strengths.append("High stated confidence")
        elif confidence < 40:
            weaknesses.append("Low stated confidence")

    session = candidate.get("session")
    if session:
        strengths.append(f"{session} session")

    return {"strengths": strengths, "weaknesses": weaknesses}


def historical_reasons(*, similar_trades_count: int, similar_win_rate: float | None, ml_available: bool) -> list[str]:
    """The "have I taken this setup before? what happened?" half of
    Phase 7 — kept separate from ``explain_trade()``'s strengths/
    weaknesses because it's about the trader's history, not the
    candidate's own fields."""
    reasons: list[str] = []
    if similar_trades_count == 0:
        reasons.append("No similar past trades found — this is a new setup for you")
    elif similar_win_rate is not None:
        reasons.append(
            f"{similar_trades_count} similar past trade{'s' if similar_trades_count != 1 else ''} found, "
            f"with a {similar_win_rate:.0f}% win rate"
        )
    if not ml_available:
        reasons.append("No trained ML model yet — this is a rule-based estimate. POST /api/v1/ml/train to enable ML predictions.")
    return reasons


def explain_trade_from_strategy(
    *, planned_rr: float | None, historical_avg_rr: float | None = None, confidence: int | None = None,
) -> dict[str, list[str]]:
    """v2 Phase 7, for the rebuilt Pre-Trade Check (only ever called
    once the ONE official strategy has already said VALID -- see
    ``app.chart.personal_averaging_strategy``, Sprint 18). Deliberately
    does NOT comment on trend/BOS/CHOCH/liquidity-sweep the way the old
    ``explain_trade`` did: the active strategy doesn't use any of
    those, so fabricating "No BOS confirmation"-style weaknesses about
    rules that don't gate anything would be misleading noise, not real
    signal. Only comments on what ML/history can actually speak to."""
    strengths: list[str] = []
    weaknesses: list[str] = []

    strengths.append(
        "Daily Bias, M15 Point of Interest, and Entry Timing all passed -- every rule in your official strategy passed"
    )

    if planned_rr is not None:
        if historical_avg_rr is not None:
            if planned_rr < historical_avg_rr - 0.3:
                weaknesses.append(
                    f"This setup's R:R ({planned_rr:.1f}) is below your historical average ({historical_avg_rr:.1f})"
                )
            else:
                strengths.append(
                    f"This setup's R:R ({planned_rr:.1f}) meets or exceeds your historical average ({historical_avg_rr:.1f})"
                )
        elif planned_rr < 1.5:
            weaknesses.append(f"R:R ({planned_rr:.1f}) is on the low side")

    if confidence is not None and confidence >= 100:
        strengths.append("Full confidence -- every step of your strategy's checklist passed with no ambiguity")

    return {"strengths": strengths, "weaknesses": weaknesses}


def analyze_pretrade_from_strategy(
    validation: dict[str, Any],
    *,
    ml_result: dict[str, Any] | None,
    similar_result: dict[str, Any],
) -> dict[str, Any]:
    """v2 Pre-Trade Check orchestration -- takes the ONE official
    strategy's own validation dict (already decided VALID by the time
    this is called) plus ML/similar-trade context, and returns ONLY
    supplementary information. Never recomputes or second-guesses
    ``validation``'s own tradeStatus/recommendation -- per the user's
    explicit rule, ML's job is limited to win-probability, similar
    trades, confidence, and repeated-mistake context."""
    ml_available = ml_result is not None
    similar_count = len(similar_result.get("similar") or [])
    similar_win_rate = similar_result.get("winRate")
    historical_avg_rr = similar_result.get("averageRR")

    win_probability = ml_result.get("winProbability") if ml_result else None
    quality_score = ml_result.get("predictedQualityScore") if ml_result else None

    ai_confidence = classify_ai_confidence(similar_trades_count=similar_count, ml_available=ml_available)
    risk_level = classify_risk_level(planned_rr=validation.get("riskReward"), historical_win_rate=similar_win_rate)
    expected_rr = compute_expected_rr(win_probability=win_probability, planned_rr=validation.get("riskReward"))
    ml_recommendation = recommend(quality_score=quality_score, ai_confidence=ai_confidence)
    reasons = historical_reasons(similar_trades_count=similar_count, similar_win_rate=similar_win_rate, ml_available=ml_available)
    explained = explain_trade_from_strategy(
        planned_rr=validation.get("riskReward"),
        historical_avg_rr=historical_avg_rr,
        confidence=validation.get("confidence"),
    )

    return {
        "trade_quality_score": quality_score,
        "win_probability": win_probability,
        "ai_confidence": ai_confidence,
        "risk_level": risk_level,
        "expected_rr": expected_rr,
        "historical_win_rate": similar_win_rate,
        "similar_trades_count": similar_count,
        "ml_recommendation": ml_recommendation,
        "strengths": explained["strengths"],
        "weaknesses": explained["weaknesses"],
        "historical_reasons": reasons,
        "ml_available": ml_available,
        "model_version": ml_result.get("modelVersion") if ml_result else None,
        "algorithm": ml_result.get("algorithm") if ml_result else None,
    }


def analyze_pretrade(
    candidate: dict[str, Any],
    *,
    ml_result: dict[str, Any] | None,
    similar_result: dict[str, Any],
) -> dict[str, Any]:
    """analyze_pretrade(candidate, ml_result=None, similar_result) —
    combines an (optional) ML prediction with historical similar-trade
    context into the full Phase 5 + Phase 7 response. ``ml_result`` is
    ``MLPredictionService.predict()``'s output, or ``None`` if the user
    hasn't trained a model yet (Phase 5 degrades gracefully rather than
    requiring Sprint 7 to be "done" first)."""
    ml_available = ml_result is not None
    # similar_result is search_similar()'s raw engine dict (camelCase:
    # "similar", "winRate", "averageRR", ...) — same shape whether it
    # arrives via SimilarService.find_similar() directly or through the
    # SimilarSearchResult Pydantic schema dumped back to a dict.
    similar_count = len(similar_result.get("similar") or [])
    similar_win_rate = similar_result.get("winRate")
    similar_avg_rr = similar_result.get("averageRR")

    if ml_available:
        # ml_result is MLPredictionService.predict()'s output (camelCase).
        quality_score = ml_result["predictedQualityScore"]
        win_probability = ml_result["winProbability"]
    else:
        # Rule-based fallback: the trade's own rule_score (0-100,
        # already computed by Sprint 6's rule engine) doubles as a
        # quality estimate until a model exists to predict one.
        quality_score = candidate.get("rule_score")
        win_probability = None

    ai_confidence = classify_ai_confidence(similar_trades_count=similar_count, ml_available=ml_available)
    risk_level = classify_risk_level(planned_rr=candidate.get("planned_rr"), historical_win_rate=similar_win_rate)
    expected_rr = compute_expected_rr(win_probability=win_probability, planned_rr=candidate.get("planned_rr"))
    recommendation = recommend(quality_score=quality_score, ai_confidence=ai_confidence)
    explanation = explain_trade(candidate, historical_avg_rr=similar_avg_rr)
    reasons = historical_reasons(
        similar_trades_count=similar_count, similar_win_rate=similar_win_rate, ml_available=ml_available
    )

    return {
        "trade_quality_score": quality_score,
        "win_probability": win_probability,
        "ai_confidence": ai_confidence,
        "risk_level": risk_level,
        "expected_rr": expected_rr,
        "historical_win_rate": similar_win_rate,
        "similar_trades_count": similar_count,
        "recommendation": recommendation,
        "strengths": explanation["strengths"],
        "weaknesses": explanation["weaknesses"],
        "historical_reasons": reasons,
        "ml_available": ml_available,
        "model_version": ml_result.get("modelVersion") if ml_result else None,
        "algorithm": ml_result.get("algorithm") if ml_result else None,
    }
