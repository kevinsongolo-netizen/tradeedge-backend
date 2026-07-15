"""ML Dataset Builder — port of ``js/ml_dataset.js``, extended per
Section 8 of the Sprint 6 architecture spec with leakage-safe historical
context columns (computed using only trades strictly earlier than the
row's own date) so the export is directly usable for Sprint 7 training.

Column names are **snake_case**, exactly matching Section 8's documented
schema (``id``, ``user_id``, ``hist_win_rate_pair``, ``y_rr_realized``,
...) — this is the ML/Python contract, deliberately distinct from the
camelCase used by the ``/api/v1/ai/*`` JSON endpoints that serve the JS
frontend (Section 6). Both the JSON and CSV export use these same keys.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

ML_DATASET_VERSION = "6.0"

#: Required for a row to be considered valid/exportable (Section 8.8).
#
# Sprint 18 note: ``rr``, ``rule_score``, ``execution_score``, and
# ``overall_score`` were dropped from this list. They come from the
# *old* H4->M15 strategy's fixed-SL/TP risk math and its rule-checklist
# scoring flow -- the active Personal Averaging Strategy has neither
# (no fixed stop loss/take profit to compute an R:R from, and no
# equivalent scoring UI yet), so every trade logged under the new
# strategy was permanently missing these fields and being excluded
# from ML training with 0 valid trades regardless of real sample size.
# The feature pipeline (app/ml/features.py) already imputes missing
# numeric values for exactly this reason, so relaxing the requirement
# here is safe -- these fields still get used as features WHEN present
# (e.g. for old-strategy trades still in someone's history), just no
# longer block a row from being a valid training example when absent.
ML_REQUIRED_FIELDS = [
    "id",
    "date",
    "pair",
    "direction",
    "asset",
    "entry",
    "pnl",
    "session",
    "outcome",
]
ML_VALID_DIRECTIONS = ["buy", "sell"]

#: Column order for JSON/CSV export (Section 8.9) — identity ->
#: instrument -> setup -> risk -> AI -> history -> target -> validation.
ML_COLUMN_ORDER = [
    "id", "user_id", "date", "dataset_version", "exported_at",
    "pair", "direction", "asset", "session", "day_of_week", "hour_of_day", "news",
    "h4_trend", "h4_poi_type", "premium_discount", "m15_confirmations", "has_bos", "has_choch", "has_liquidity_sweep", "confidence",
    "entry", "stop_loss", "take_profit", "lots", "planned_rr", "exit", "pnl", "rr", "exit_reason", "emotion", "followed_plan", "rules_followed",
    "rule_score", "execution_score", "overall_score", "rule_recommendation", "execution_grade",
    "hist_trades_total", "hist_trades_pair", "hist_trades_session", "hist_win_rate_all", "hist_win_rate_pair", "hist_win_rate_session",
    "hist_expectancy_all", "hist_avg_rr_all", "hist_streak_dir", "hist_rule_score_ema10", "hist_execution_score_ema10",
    "outcome", "y_win", "y_pnl", "y_rr_realized", "y_quality_bucket",
    "validation_status", "validation_errors", "validation_warnings",
]


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        n = float(value)
        return n if n == n else None  # filter NaN
    except (TypeError, ValueError):
        return None


def _score(entry: dict, key: str) -> float | None:
    if isinstance(entry.get(key), (int, float)) and not isinstance(entry.get(key), bool):
        return entry[key]
    ai = entry.get("ai")
    if isinstance(ai, dict) and isinstance(ai.get(key), (int, float)):
        return ai[key]
    return None


def _outcome(entry: dict) -> str:
    pnl = entry.get("pnl") or 0
    return "Win" if pnl > 0 else "Loss" if pnl < 0 else "Breakeven"


def _quality_bucket(overall_score: float | None) -> str:
    if overall_score is None:
        return "D"
    if overall_score >= 90:
        return "A"
    if overall_score >= 80:
        return "B"
    if overall_score >= 70:
        return "C"
    return "D"


def _ema(values: list[float], span: int) -> float | None:
    """Simple trailing EMA over up to the last ``span`` values, matching
    a standard exponential moving average (alpha = 2/(span+1))."""
    if not values:
        return None
    alpha = 2 / (span + 1)
    ema = values[0]
    for v in values[1:]:
        ema = alpha * v + (1 - alpha) * ema
    return ema


def _planned_rr(entry: dict) -> float | None:
    entry_p, sl, tp = _num(entry.get("entry")), _num(entry.get("sl")), _num(entry.get("tp"))
    if entry_p is None or sl is None or tp is None or entry_p == sl:
        return None
    risk = abs(entry_p - sl)
    reward = abs(tp - entry_p)
    return (reward / risk) if risk > 0 else None


def build_dataset(entries: list[dict] | None, *, exported_at: str | None = None, user_id: int = 1) -> list[dict]:
    """build_dataset(entries) — flattens journal entries into ML-ready
    rows (Section 8), including leakage-safe historical columns computed
    in a single chronological pass (each row only "sees" strictly
    earlier trades, per Section 8.6)."""
    entries = entries or []
    chronological = sorted(entries, key=lambda e: (str(e.get("date") or ""), str(e.get("id") or "")))

    rows: list[dict] = []
    prior: list[dict] = []
    rule_history: list[float] = []
    exec_history: list[float] = []
    running_win_streak = 0
    running_loss_streak = 0

    for entry in chronological:
        pair = str(entry["pair"]).upper() if entry.get("pair") else None
        same_pair_prior = [e for e in prior if e.get("pair") and pair and str(e["pair"]).upper() == pair]
        same_session_prior = [e for e in prior if e.get("session") and entry.get("session") and e["session"] == entry["session"]]

        def wr(rows_: list[dict], min_n: int) -> float | None:
            return (len([e for e in rows_ if (e.get("pnl") or 0) > 0]) / len(rows_)) if len(rows_) >= min_n else None

        hist_win_rate_all = wr(prior, 5)
        hist_win_rate_pair = wr(same_pair_prior, 3)
        hist_win_rate_session = wr(same_session_prior, 3)
        hist_expectancy_all = (sum(float(e.get("pnl") or 0) for e in prior) / len(prior)) if prior else None
        prior_rr = [v for v in (_num(e.get("rr")) for e in prior) if v is not None]
        hist_avg_rr_all = (sum(prior_rr) / len(prior_rr)) if prior_rr else None

        rule_score = _score(entry, "ruleScore")
        execution_score = _score(entry, "executionScore")
        overall_score = _score(entry, "overallScore")

        date_str = entry.get("date")
        day_of_week = None
        try:
            day_of_week = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").weekday() if date_str else None
        except ValueError:
            day_of_week = None

        m15 = entry.get("m15Confirmations") or []
        pnl = _num(entry.get("pnl")) or 0.0
        rr_val = _num(entry.get("rr")) or 0.0
        outcome = _outcome(entry)

        row = {
            "id": entry.get("id"),
            "user_id": user_id,
            "date": date_str,
            "dataset_version": ML_DATASET_VERSION,
            "exported_at": exported_at,
            "pair": pair,
            "direction": entry.get("direction"),
            "asset": entry.get("asset"),
            "session": entry.get("session"),
            "day_of_week": day_of_week,
            "hour_of_day": None,
            "news": entry.get("news"),
            "h4_trend": entry.get("h4Trend"),
            "h4_poi_type": entry.get("h4PoiType"),
            "premium_discount": entry.get("premiumDiscount"),
            "m15_confirmations": "|".join(m15) if m15 else "",
            "has_bos": 1 if "BOS" in m15 else 0,
            "has_choch": 1 if "CHOCH" in m15 else 0,
            "has_liquidity_sweep": 1 if "Liquidity Sweep" in m15 else 0,
            "confidence": _num(entry.get("confidence")),
            "entry": _num(entry.get("entry")),
            "stop_loss": _num(entry.get("sl")),
            "take_profit": _num(entry.get("tp")),
            "lots": _num(entry.get("lots")),
            "planned_rr": _planned_rr(entry),
            "exit": _num(entry.get("exit")),
            "pnl": pnl,
            "rr": rr_val,
            "exit_reason": entry.get("exitReason"),
            "emotion": entry.get("emotion"),
            "followed_plan": entry.get("followedPlan"),
            "rules_followed": entry.get("rulesFollowed"),
            "rule_score": rule_score,
            "execution_score": execution_score,
            "overall_score": overall_score,
            "rule_recommendation": entry.get("ruleRecommendation"),
            "execution_grade": entry.get("executionGrade"),
            "hist_trades_total": len(prior),
            "hist_trades_pair": len(same_pair_prior),
            "hist_trades_session": len(same_session_prior),
            "hist_win_rate_all": hist_win_rate_all,
            "hist_win_rate_pair": hist_win_rate_pair,
            "hist_win_rate_session": hist_win_rate_session,
            "hist_expectancy_all": hist_expectancy_all,
            "hist_avg_rr_all": hist_avg_rr_all,
            "hist_streak_dir": running_win_streak if running_win_streak > 0 else (-running_loss_streak if running_loss_streak > 0 else 0),
            "hist_rule_score_ema10": _ema(rule_history[-10:], 10) if rule_history else None,
            "hist_execution_score_ema10": _ema(exec_history[-10:], 10) if exec_history else None,
            "outcome": outcome,
            "y_win": 1 if pnl > 0 else 0,
            "y_pnl": pnl,
            "y_rr_realized": rr_val,
            "y_quality_bucket": _quality_bucket(overall_score),
            "validation_status": "unchecked",
            "validation_errors": "",
            "validation_warnings": "",
        }
        validation = validate_row(row)
        row["validation_status"] = "valid" if validation["valid"] else "rejected"
        row["validation_errors"] = "|".join(validation["errors"])
        row["validation_warnings"] = "|".join(validation["warnings"])
        rows.append(row)

        # Update running state for the *next* iteration only (this row's
        # own outcome must never leak into its own history columns).
        prior.append(entry)
        if rule_score is not None:
            rule_history.append(rule_score)
        if execution_score is not None:
            exec_history.append(execution_score)
        if pnl > 0:
            running_win_streak += 1
            running_loss_streak = 0
        elif pnl < 0:
            running_loss_streak += 1
            running_win_streak = 0

    return rows


def validate_row(row: dict) -> dict:
    """validate_row(row) — validates one flattened training row.
    Invalid rows are excluded from the exported dataset."""
    errors: list[str] = []
    warnings: list[str] = []
    for field in ML_REQUIRED_FIELDS:
        if row.get(field) in (None, ""):
            errors.append(f"Missing {field}")
    if row.get("direction") and row["direction"] not in ML_VALID_DIRECTIONS:
        errors.append("Invalid direction")
    for field in ("entry", "exit", "pnl", "rr", "rule_score", "execution_score", "overall_score"):
        value = row.get(field)
        if value is not None and not isinstance(value, (int, float)):
            errors.append(f"Invalid numeric {field}")
    rr = row.get("rr")
    if isinstance(rr, (int, float)) and rr <= 0:
        errors.append("RR must be positive")
    if not row.get("m15_confirmations"):
        warnings.append("Missing M15 confirmations")
    if row.get("confidence") is None:
        warnings.append("Missing confidence")
    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def validate_dataset(dataset: list[dict] | None) -> dict:
    """validate_dataset(dataset) — per-row validation report + overall
    quality score (Section 4.7's ``/ml/validate``)."""
    rows = [{"index": i, **validate_row(row)} for i, row in enumerate(dataset or [])]
    valid_count = len([r for r in rows if r["valid"]])
    total = len(rows)
    return {
        "total": total,
        "validCount": valid_count,
        "invalidCount": total - valid_count,
        "rows": rows,
        "qualityScore": round((valid_count / total) * 100) if total else 0,
    }


def _csv_escape(value: Any) -> str:
    if isinstance(value, list):
        value = "|".join(str(v) for v in value)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def to_csv(dataset: list[dict] | None) -> str:
    """to_csv(rows) — UTF-8, LF line endings, header matches
    ``ML_COLUMN_ORDER`` exactly (Section 8.9)."""
    rows = dataset or []
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(ML_COLUMN_ORDER)
    for row in rows:
        writer.writerow([_csv_escape(row.get(col)) for col in ML_COLUMN_ORDER])
    return buffer.getvalue()
