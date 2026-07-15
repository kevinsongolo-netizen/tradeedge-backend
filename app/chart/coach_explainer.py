"""Plain-language explanation + confidence scoring (Chart Analysis
Engine — Level 3, "AI Trading Coach").

v2 — rewritten to be a thin narrator over the ONE official strategy's
own validation dict (``app.chart.htf_ltf_ob_strategy.validate_h4_m15_ob``),
never a second, independent scorer. The old version computed its own
"trend alignment"/"BOS quality"/"CHOCH quality" scores from
``ChartAnalysis`` directly — that meant the Chart Analysis Engine could
show two different, disagreeing pictures of the same trade (the
validator's real reasons vs. this module's own trend/BOS/CHOCH-based
narrative). Per the user's explicit instruction ("only one official
strategy module ... I do not want duplicate strategy logic"), this
module now does no independent trade-quality judgement at all: it only
turns ``validation``'s own fields (tradeStatus, direction, confidence,
reasonsPassed/Failed, ruleChecks) into readable sentences. Pure
function, no I/O.
"""
from __future__ import annotations

from app.schemas.chart import ChartAnalysis

_STATUS_SCORE = {"PASSED": 100, "FAILED": 0, "NOT_CHECKED": 0}
_RULE_TO_FIELD = {
    "H4 Order Block/FVG": "h4_poi",
    "M15 Order Block/FVG": "m15_poi",
    "POI Alignment": "poi_alignment",
    "Entry / SL / TP": "entry_target",
}


def build_confidence_breakdown(analysis: ChartAnalysis, validation: dict, min_rr: float = 2.0) -> dict:
    """Reads the funnel's own ``ruleChecks`` (added in
    ``htf_ltf_ob_strategy`` v3) and turns each step into a 0/100 score
    plus the strategy's own overall confidence -- no separate
    trend/BOS/CHOCH/FVG/RR scoring of any kind. ``analysis`` and
    ``min_rr`` are accepted only to keep this function's signature
    stable for existing callers; neither is used for scoring anymore."""
    del analysis, min_rr  # kept for call-site compatibility only
    fields = {"h4_poi": 0, "m15_poi": 0, "poi_alignment": 0, "entry_target": 0}
    for check in validation.get("ruleChecks") or []:
        field = _RULE_TO_FIELD.get(check.get("rule"))
        if field is not None:
            fields[field] = _STATUS_SCORE.get(check.get("status"), 0)

    return {
        **fields,
        "overall": validation.get("confidence", 0),
    }


def explain(analysis: ChartAnalysis, validation: dict, min_rr: float = 2.0) -> dict:
    """Narrates ``validation`` (the single source of truth for whether
    this is a real trade) in full sentences. ``analysis`` is only used
    for the current price / premium-discount context line -- never to
    re-decide anything the strategy already decided."""
    del min_rr  # no min-R:R gate in the active strategy; kept for signature compatibility
    direction = validation.get("direction")
    is_valid = validation.get("tradeStatus") == "VALID"
    confidence = build_confidence_breakdown(analysis, validation)

    explanation: list[str] = []
    for check in validation.get("ruleChecks") or []:
        icon = "✓" if check.get("status") == "PASSED" else ("✗" if check.get("status") == "FAILED" else "—")
        explanation.append(f"{icon} {check.get('rule')}: {check.get('detail')}")

    if is_valid and direction is not None:
        headline = f"{direction.upper()} ANALYSIS"
        rr = validation.get("riskReward")
        if rr is not None:
            explanation.append(f"Risk:Reward works out to 1:{rr:.1f} at current structure.")
        explanation.append("Every step of your H4→M15 POI strategy passed — this is a real setup, not a guess.")
        recommendation = direction.upper()
    else:
        headline = "WAIT"
        explanation.append("Your H4→M15 POI strategy hasn't fully lined up yet — see which rule above is still pending.")
        recommendation = "WAIT"

    return {
        "headline": headline,
        "explanation": explanation,
        "confidence": confidence,
        "recommendation": recommendation,
    }
