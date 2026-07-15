"""Plain-language explanation + confidence scoring (Chart Analysis
Engine — Level 3, "AI Trading Coach").

v3 (Sprint 18) — the active strategy switched from the H4->M15 POI
engine to the Personal Averaging Strategy (Daily Bias / M15 POI /
Entry Timing / Add-On Entry), but this module's own job hasn't
changed: it's a thin narrator over ``validation``'s own fields
(tradeStatus, direction, confidence, reasonsPassed/Failed, ruleChecks,
strategy, dailyBias, addOnSignal, breakEvenPrice), never a second,
independent judge of trade quality. Reads ``validation["strategy"]``
for the narrative text so this module doesn't hard-code which engine
produced it. Pure function, no I/O.
"""
from __future__ import annotations

from app.schemas.chart import ChartAnalysis

_STATUS_SCORE = {"PASSED": 100, "FAILED": 0, "NOT_CHECKED": 0}
_RULE_TO_FIELD = {
    "Daily Bias": "daily_bias",
    "M15 Order Block/FVG": "m15_poi",
    "Entry Timing (near end of zone)": "entry_timing",
    "Add-On Entry (2nd position)": "add_on",
}
_DEFAULT_STRATEGY_LABEL = "your official strategy"


def build_confidence_breakdown(analysis: ChartAnalysis, validation: dict, min_rr: float = 2.0) -> dict:
    """Reads the funnel's own ``ruleChecks`` and turns each step into a
    0/100 score plus the strategy's own overall confidence -- no
    separate scoring of any kind. ``analysis`` and ``min_rr`` are
    accepted only to keep this function's signature stable for
    existing callers; neither is used for scoring."""
    del analysis, min_rr  # kept for call-site compatibility only
    fields = {"daily_bias": 0, "m15_poi": 0, "entry_timing": 0, "add_on": 0}
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
    is_add_on = bool(validation.get("addOnSignal"))
    strategy_label = validation.get("strategy") or _DEFAULT_STRATEGY_LABEL
    confidence = build_confidence_breakdown(analysis, validation)

    explanation: list[str] = []
    for check in validation.get("ruleChecks") or []:
        icon = "✓" if check.get("status") == "PASSED" else ("✗" if check.get("status") == "FAILED" else "—")
        explanation.append(f"{icon} {check.get('rule')}: {check.get('detail')}")

    if is_valid and is_add_on and direction is not None:
        headline = f"ADD-ON {direction.upper()}"
        explanation.append(
            f"Every step of {strategy_label} passed, including rule 3's add-on trigger -- "
            "this is the signal for your 2nd, same-size entry, not a fresh first trade."
        )
        recommendation = "ADD"
    elif is_valid and direction is not None:
        headline = f"{direction.upper()} ANALYSIS"
        explanation.append(f"Every step of {strategy_label} passed -- this is a real setup, not a guess.")
        recommendation = direction.upper()
    else:
        headline = "WAIT"
        explanation.append(f"{strategy_label} hasn't fully lined up yet -- see which rule above is still pending.")
        recommendation = "WAIT"

    break_even = validation.get("breakEvenPrice")
    if break_even is not None:
        explanation.append(
            f"Break-even/small-profit exit level for your open entries: {break_even:.5f} "
            "-- rule 4's \"never close in lost\", made concrete."
        )

    return {
        "headline": headline,
        "explanation": explanation,
        "confidence": confidence,
        "recommendation": recommendation,
    }
