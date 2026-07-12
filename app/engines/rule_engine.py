"""Rule Engine — port of ``js/rule_engine.js``.

Scores a trade 0-100 against the strategy rules. Pure function: no DB,
no HTTP, no side effects (Section 5.1's engine contract). Weight
normalization, scoring, and recommendation thresholds are ported
verbatim from the JS version.
"""
from __future__ import annotations

from typing import Any

from app.engines.reason_engine import generate_reason

RULE_ENGINE_VERSION = "6.0"

DEFAULT_RULE_SCORE_WEIGHTS: dict[str, float] = {
    "h4Trend": 10,
    "h4Poi": 10,
    "premiumDiscount": 8,
    "m15Confirmation": 8,
    "bos": 8,
    "choch": 8,
    "liquiditySweep": 8,
    "session": 8,
    "rr": 12,
    "news": 8,
    "confidence": 6,
    "followedPlan": 6,
}


def _to_float(value: Any) -> float | None:
    """parseFloat(value) -> float|None, matching JS's lenient parsing
    semantics (empty/garbage -> null, not a raised error)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has(value: Any) -> bool:
    """JS ``value !== undefined && value !== null && String(value).trim() !== ''``."""
    return value is not None and str(value).strip() != ""


def _normalize_tags(tags: Any) -> list[str]:
    if not isinstance(tags, list):
        return []
    return [str(t).strip() for t in tags if str(t).strip()]


def normalize_rule_weights(weights: dict[str, float] | None = None) -> dict[str, float]:
    """Merges ``weights`` over the defaults and rescales so the total is
    always 100 (matches JS ``normalizeRuleWeights``)."""
    merged = {**DEFAULT_RULE_SCORE_WEIGHTS, **(weights or {})}
    total = sum(float(v) or 0 for v in merged.values()) or 1
    return {k: (float(v) or 0) / total * 100 for k, v in merged.items()}


def _check(key: str, ok: bool, partial: bool, context: dict) -> dict:
    outcome = "pass" if ok else "partial" if partial else "fail"
    return {
        "key": key,
        "ok": bool(ok),
        "partial": bool(partial) and not ok,
        "text": generate_reason(key, outcome, context),
    }


def compute_rule_score(trade: dict[str, Any] | None, weights: dict[str, float] | None = None) -> dict:
    """computeRuleScore(trade, weights=None)

    Evaluates H4 trend, POI, premium/discount, M15 confirmations, BOS,
    CHOCH, liquidity sweep, session, RR, news, confidence, and plan
    adherence. Returns the full breakdown plus the legacy
    ``{score, reasons}``-shaped fields the frontend originally used.
    """
    fields = trade or {}
    active_weights = normalize_rule_weights(weights)
    m15 = _normalize_tags(fields.get("m15Confirmations"))
    rr_val = _to_float(fields.get("rr"))
    confidence_val = _to_float(fields.get("confidence"))
    if confidence_val is not None and confidence_val <= 10:
        confidence_val = confidence_val * 10

    checks: list[dict] = []
    score = 0.0

    def add(key: str, points: float, check: dict) -> None:
        nonlocal score
        value = points if check["ok"] else (points / 2 if check["partial"] else 0)
        score += value
        checks.append({**check, "points": round(value), "maxPoints": round(points)})

    add("h4Trend", active_weights["h4Trend"], _check("h4Trend", _has(fields.get("h4Trend")), False, fields))
    add("h4Poi", active_weights["h4Poi"], _check("h4Poi", _has(fields.get("h4PoiType")), False, fields))
    add(
        "premiumDiscount",
        active_weights["premiumDiscount"],
        _check("premiumDiscount", _has(fields.get("premiumDiscount")), False, fields),
    )
    add(
        "m15Confirmation",
        active_weights["m15Confirmation"],
        _check("m15Confirmation", len(m15) > 0, False, {**fields, "m15Confirmations": m15}),
    )
    add("bos", active_weights["bos"], _check("bos", "BOS" in m15, False, fields))
    add("choch", active_weights["choch"], _check("choch", "CHOCH" in m15, False, fields))
    add(
        "liquiditySweep",
        active_weights["liquiditySweep"],
        _check("liquiditySweep", "Liquidity Sweep" in m15, False, fields),
    )
    add("session", active_weights["session"], _check("session", _has(fields.get("session")), False, fields))

    rr_ok = rr_val is not None and rr_val >= 2
    rr_partial = rr_val is not None and 1 <= rr_val < 2
    add("rr", active_weights["rr"], _check("rr", rr_ok, rr_partial, {"rrVal": rr_val or 0}))

    news = fields.get("news") or "None"
    add("news", active_weights["news"], _check("news", news != "High", news == "Medium", {"news": news}))

    confidence_ok = confidence_val is not None and confidence_val >= 70
    confidence_partial = confidence_val is not None and 50 <= confidence_val < 70
    add(
        "confidence",
        active_weights["confidence"],
        _check("confidence", confidence_ok, confidence_partial, {"confidence": confidence_val or 0}),
    )

    followed_plan = fields.get("followedPlan") or ""
    add(
        "followedPlan",
        active_weights["followedPlan"],
        _check("followedPlan", followed_plan == "Yes", followed_plan == "Partial", fields),
    )

    score = max(0, min(100, round(score)))
    recommendation = "TAKE" if score >= 80 else "CAUTION" if score >= 60 else "SKIP"
    missing_confirmations = [c["text"] for c in checks if not c["ok"]]

    return {
        "ruleScore": score,
        "score": score,
        "recommendation": recommendation,
        "reasons": checks,
        "passedReasons": [c["text"] for c in checks if c["ok"]],
        "missingConfirmations": missing_confirmations,
        "missing": missing_confirmations,
        "ruleVersion": RULE_ENGINE_VERSION,
        "weights": active_weights,
    }


def calculate_rule_score(trade: dict[str, Any] | None, weights: dict[str, float] | None = None) -> dict:
    """calculateRuleScore(trade, weights=None) — spec-shaped wrapper
    around ``compute_rule_score`` (kept for parity with the JS API)."""
    result = compute_rule_score(trade or {}, weights)
    return {
        "ruleScore": result["score"],
        "score": result["score"],
        "recommendation": result["recommendation"],
        "reasons": result["passedReasons"],
        "missingConfirmations": result["missingConfirmations"],
        "missing": result["missingConfirmations"],
        "ruleVersion": result["ruleVersion"],
        "weights": result["weights"],
    }
