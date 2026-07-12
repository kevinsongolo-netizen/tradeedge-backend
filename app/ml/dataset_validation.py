"""Sprint 7 Phase 1 — Dataset-level validation report.

Builds on Sprint 6's per-row validation (``app/engines/ml_dataset.py``'s
``validate_row``/``ML_REQUIRED_FIELDS``) rather than duplicating it: this
module consumes the already-validated flattened rows produced by
``MLService.build()`` (each row already carries ``validation_status``,
``validation_errors``, ``validation_warnings`` from Sprint 6) and adds
the dataset-wide view Sprint 6 didn't have — missing-field counts,
duplicate detection, and class distribution — needed before any
training run (Phase 1 must run, and must reject, before Phase 3 trains
anything).
"""
from __future__ import annotations

from collections import Counter
from typing import Any

#: Minimum number of *valid* rows required before a training run is
#: allowed (Phase 3's "do not overfit" — a model trained on a handful
#: of rows is meaningless and will look artificially perfect).
MIN_TRAINING_ROWS = 30


def _missing_field_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Tallies which fields were reported missing across all rows, by
    parsing Sprint 6's pipe-delimited ``validation_errors`` strings
    (e.g. ``"Missing pnl|Missing rr"``) rather than re-checking fields
    ourselves — one source of truth for "what counts as missing".
    """
    counts: Counter[str] = Counter()
    for row in rows:
        errors = row.get("validation_errors") or ""
        for err in errors.split("|"):
            err = err.strip()
            if err.startswith("Missing "):
                counts[err[len("Missing "):]] += 1
    return dict(counts.most_common())


def _duplicate_ids(rows: list[dict[str, Any]]) -> list[str]:
    """Rows sharing the same ``id`` are duplicates (the same trade
    exported/counted twice — e.g. a bad bulk-import retry). Returns the
    ids that appear more than once."""
    ids = [row.get("id") for row in rows if row.get("id")]
    counts = Counter(ids)
    return [i for i, n in counts.items() if n > 1]


def _class_distribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = Counter(row.get("outcome") or "Unknown" for row in rows)
    total = len(rows)
    wins = outcomes.get("Win", 0)
    losses = outcomes.get("Loss", 0)
    breakeven = outcomes.get("Breakeven", 0)
    return {
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "winRate": round((wins / total) * 100, 2) if total else 0.0,
        "isBalanced": bool(total) and min(wins, losses) / total >= 0.2 if total else False,
    }


def generate_validation_report(rows: list[dict[str, Any]] | None) -> dict[str, Any]:
    """generate_validation_report(rows) — Phase 1's deliverable.

    ``rows`` is the output of ``MLService.build()`` (every row the user
    has, valid and invalid alike — each already carries Sprint 6's
    ``validation_status``). Returns:

    - ``totalTrades`` / ``validTrades`` / ``invalidTrades``
    - ``missingFields`` — ``{field_name: count}``, most common first
    - ``duplicateTrades`` — count and the offending ids
    - ``classDistribution`` — wins/losses/breakeven + win rate
    - ``readyForTraining`` — whether Phase 3 is allowed to run, plus
      ``reason`` if not.
    """
    rows = rows or []
    total = len(rows)
    valid_rows = [r for r in rows if r.get("validation_status") == "valid"]
    invalid_rows = [r for r in rows if r.get("validation_status") != "valid"]
    duplicate_ids = _duplicate_ids(rows)

    valid_count = len(valid_rows)
    ready = valid_count >= MIN_TRAINING_ROWS
    if not ready:
        reason = (
            f"Only {valid_count} valid trade(s) available; at least "
            f"{MIN_TRAINING_ROWS} are required to train a model without "
            "overfitting."
        )
    else:
        reason = None

    return {
        "totalTrades": total,
        "validTrades": valid_count,
        "invalidTrades": len(invalid_rows),
        "missingFields": _missing_field_counts(rows),
        "duplicateTrades": {
            "count": len(duplicate_ids),
            "ids": duplicate_ids,
        },
        "classDistribution": _class_distribution(valid_rows),
        "minTrainingRows": MIN_TRAINING_ROWS,
        "readyForTraining": ready,
        "reason": reason,
    }
