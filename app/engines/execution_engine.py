"""Execution Engine — port of ``js/execution_engine.js``.

Scores trade management and discipline 0-100. Pure function: no DB, no
HTTP access. ``journal_context`` is the user's prior trades, used only
for the same-day overtrading check.
"""
from __future__ import annotations

from typing import Any

EXECUTION_ENGINE_VERSION = "6.0"

EXECUTION_SCORE_WEIGHTS: dict[str, int] = {
    "entryQuality": 10,
    "stopLossRespected": 10,
    "takeProfitRespected": 9,
    "closedEarly": 10,
    "lateEntry": 8,
    "movedStopLoss": 8,
    "movedTakeProfit": 6,
    "followedExitPlan": 11,
    "emotionalExit": 9,
    "overtrading": 7,
    "revengeTrading": 6,
    "fomo": 6,
}

_EXIT_PLAN_REASONS = {
    "Take Profit Hit",
    "Stop Loss Hit",
    "Manual Close - Target Reached",
    "Manual Close - Structure Break/Invalidation",
    "Manual Close - News Event",
    "Manual Close - New POI Formed (Lower TF)",
    "Trailing Stop",
}


def _text_contains(trade: dict[str, Any], terms: list[str]) -> bool:
    parts = [
        trade.get("notes"),
        trade.get("worked"),
        trade.get("failed"),
        *(trade.get("workedTags") or []),
        *(trade.get("failedTags") or []),
    ]
    haystack = " ".join(str(p) for p in parts if p is not None).lower()
    return any(term.lower() in haystack for term in terms)


def _numeric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def execution_outcome_grade(score: int) -> str:
    if score >= 90:
        return "EXCELLENT"
    if score >= 80:
        return "GOOD"
    if score >= 70:
        return "FAIR"
    return "POOR"


def _check(key: str, ok: bool, label: str, suggestion: str = "") -> dict:
    return {"key": key, "ok": bool(ok), "text": label, "suggestion": suggestion or ""}


def compute_execution_score(
    trade: dict[str, Any] | None, journal_context: list[dict[str, Any]] | None = None
) -> dict:
    """computeExecutionScore(trade, journal_context)

    Evaluates entry quality, SL/TP respect, early close, moved SL/TP,
    exit plan adherence, emotional exit, overtrading, revenge trading,
    and FOMO.
    """
    fields = trade or {}
    checks: list[dict] = []
    score = 0

    def add(key: str, points: int, ok: bool, label: str, suggestion: str = "") -> None:
        nonlocal score
        if ok:
            score += points
        checks.append({**_check(key, ok, label, suggestion), "points": points if ok else 0, "maxPoints": points})

    rr = _numeric(fields.get("rr"))
    has_entry_plan = _has(fields.get("entry")) and _has(fields.get("sl")) and _has(fields.get("tp")) and rr is not None
    entry_quality_ok = has_entry_plan and rr >= 1
    add(
        "entryQuality",
        EXECUTION_SCORE_WEIGHTS["entryQuality"],
        entry_quality_ok,
        "Entry had price, SL, TP, and usable RR" if entry_quality_ok else "Entry plan was incomplete or RR was below 1R",
        "Record entry, SL, TP, and keep RR above 1R before taking the trade.",
    )

    exit_reason = fields.get("exitReason") or ""
    sl_respected = (
        not _text_contains(fields, ["moved sl wider", "widened stop", "removed stop", "no stop"])
        and exit_reason != "Other"
    )
    add(
        "stopLossRespected",
        EXECUTION_SCORE_WEIGHTS["stopLossRespected"],
        sl_respected,
        "Stop loss was respected" if sl_respected else "Stop loss discipline risk detected",
        "Do not widen or remove the stop after entry.",
    )

    tp_respected = (
        not _text_contains(fields, ["moved tp closer", "cut target", "reduced target"])
        and exit_reason != "Manual Close - Fear/Uncertainty"
    )
    add(
        "takeProfitRespected",
        EXECUTION_SCORE_WEIGHTS["takeProfitRespected"],
        tp_respected,
        "Take-profit plan was respected" if tp_respected else "Take-profit plan was not respected",
        "Avoid shrinking the target without a planned structural reason.",
    )

    closed_early = exit_reason == "Manual Close - Fear/Uncertainty" or _text_contains(
        fields, ["early exit", "closed early", "panic close"]
    )
    add(
        "closedEarly",
        EXECUTION_SCORE_WEIGHTS["closedEarly"],
        not closed_early,
        "Closed early" if closed_early else "No early close detected",
        "Let planned exits work unless structure invalidates the trade.",
    )

    late_entry = _text_contains(fields, ["late entry", "chased", "entered late", "missed entry"]) or fields.get(
        "emotion"
    ) == "FOMO"
    add(
        "lateEntry",
        EXECUTION_SCORE_WEIGHTS["lateEntry"],
        not late_entry,
        "Late entry / chasing detected" if late_entry else "No late entry detected",
        "Skip late entries unless the setup fully re-confirms at a fresh level.",
    )

    moved_sl = _text_contains(fields, ["moved sl", "moved stop", "widened stop", "stop moved"])
    add(
        "movedStopLoss",
        EXECUTION_SCORE_WEIGHTS["movedStopLoss"],
        not moved_sl,
        "Moved stop loss after entry" if moved_sl else "No unplanned stop-loss move detected",
        "Only move SL according to a predefined management rule.",
    )

    moved_tp = _text_contains(fields, ["moved tp", "moved target", "target moved"])
    add(
        "movedTakeProfit",
        EXECUTION_SCORE_WEIGHTS["movedTakeProfit"],
        not moved_tp,
        "Moved take profit after entry" if moved_tp else "No unplanned take-profit move detected",
        "Only adjust TP when your written exit plan allows it.",
    )

    followed_exit_plan = exit_reason in _EXIT_PLAN_REASONS
    add(
        "followedExitPlan",
        EXECUTION_SCORE_WEIGHTS["followedExitPlan"],
        followed_exit_plan,
        "Exit followed a defined plan reason" if followed_exit_plan else "Exit plan was missing or unclear",
        "Choose a planned exit reason for every closed trade.",
    )

    emotional_exit = exit_reason == "Manual Close - Fear/Uncertainty" or fields.get("emotion") in (
        "FOMO",
        "Revenge",
        "Anxious",
    )
    add(
        "emotionalExit",
        EXECUTION_SCORE_WEIGHTS["emotionalExit"],
        not emotional_exit,
        "Emotional exit/trade state detected" if emotional_exit else "No emotional exit detected",
        "Pause after emotional trades and require confirmation before the next entry.",
    )

    same_day_trades = len(
        [e for e in (journal_context or []) if e.get("date") and fields.get("date") and e["date"] == fields["date"]]
    )
    overtrading = same_day_trades >= 4 or _text_contains(fields, ["overtrade", "over trading", "too many trades"])
    add(
        "overtrading",
        EXECUTION_SCORE_WEIGHTS["overtrading"],
        not overtrading,
        "Overtrading risk detected" if overtrading else "No overtrading risk detected",
        "Set a daily trade limit and stop when it is reached.",
    )

    revenge = fields.get("emotion") == "Revenge" or _text_contains(fields, ["revenge"])
    add(
        "revengeTrading",
        EXECUTION_SCORE_WEIGHTS["revengeTrading"],
        not revenge,
        "Revenge trading detected" if revenge else "No revenge trading detected",
        "Stop trading after revenge impulses or after hitting your loss limit.",
    )

    fomo = fields.get("emotion") == "FOMO" or _text_contains(fields, ["fomo", "chased", "late entry"])
    add(
        "fomo",
        EXECUTION_SCORE_WEIGHTS["fomo"],
        not fomo,
        "FOMO/chasing detected" if fomo else "No FOMO detected",
        "Require setup confirmation before entry and avoid late entries.",
    )

    score = max(0, min(100, round(score)))
    strengths = [c["text"] for c in checks if c["ok"]]
    mistakes = [c["text"] for c in checks if not c["ok"]]
    suggestions = list(dict.fromkeys(c["suggestion"] for c in checks if not c["ok"] and c["suggestion"]))
    grade = execution_outcome_grade(score)

    return {
        "executionScore": score,
        "score": score,
        "grade": grade,
        "strengths": strengths,
        "mistakes": mistakes,
        "suggestions": suggestions,
        "reasons": checks,
        "executionVersion": EXECUTION_ENGINE_VERSION,
    }


def combine_scores(rule_score: float | None, execution_score: float | None) -> int | None:
    """combineScores(ruleScore, executionScore)

    Overall score is 50% Rule Score + 50% Execution Score, capped to
    0-100. Falls back to whichever single score is available.
    """
    has_rule = isinstance(rule_score, (int, float)) and rule_score is not None
    has_exec = isinstance(execution_score, (int, float)) and execution_score is not None
    if has_rule and has_exec:
        return max(0, min(100, round((rule_score + execution_score) / 2)))
    if has_rule:
        return max(0, min(100, round(rule_score)))
    if has_exec:
        return max(0, min(100, round(execution_score)))
    return None


def score_band(score: float | None) -> dict:
    """scoreBand(score) — label + color band for a 0-100 score. Pure UI
    presentation helper; ported for parity since some ML/coach views
    reuse the label text."""
    if score is None:
        return {"label": "Unknown", "color": "var(--text-muted)"}
    if score >= 90:
        return {"label": "Excellent", "color": "var(--green)"}
    if score >= 80:
        return {"label": "Good", "color": "var(--accent)"}
    if score >= 70:
        return {"label": "Fair", "color": "#eab308"}
    return {"label": "Poor", "color": "var(--red)"}
