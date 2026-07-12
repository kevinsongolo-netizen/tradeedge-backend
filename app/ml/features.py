"""Sprint 7 Phase 2 — Feature engineering.

Turns Sprint 6's flattened ML rows (``app/engines/ml_dataset.py``'s
``build_dataset()`` output) into the feature matrix the training
pipeline (``app/ml/train.py``) and the prediction service
(``app/ml/predict.py``) both consume. Categorical encoding and numeric
scaling live *inside* the persisted scikit-learn ``Pipeline`` (built by
``build_preprocessor()``) rather than as a separate hand-rolled step —
that way the exact same fitted encoders/scaler used at training time
are automatically reapplied at prediction time (no train/serve skew),
and the whole thing is one ``joblib``-picklable object (Phase 6).

One feature Sprint 6's dataset doesn't already have is added here:
``hist_strategy_health_score`` — a leakage-safe, point-in-time strategy
health score (reusing Sprint 6's ``compute_strategy_health`` engine,
unmodified) computed from only the trades strictly before each row.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.engines.ml_dataset import build_dataset
from app.engines.strategy_health_engine import compute_strategy_health

#: "Pair, Asset, Direction, Session, H4 Trend, POI" (categorical, one-hot encoded).
CATEGORICAL_FEATURES = [
    "pair",
    "asset",
    "direction",
    "session",
    "h4_trend",
    "h4_poi_type",
    "emotion",  # "Psychology"
]

#: "BOS, CHOCH, Liquidity Sweep, Risk:Reward, Rule Score, Execution
#: Score, Confidence" + the leakage-safe rolling history columns
#: ("learn from the user's own trading history") + Strategy Health.
NUMERIC_FEATURES = [
    "has_bos",
    "has_choch",
    "has_liquidity_sweep",
    "planned_rr",  # pre-trade RR (known before the outcome) — see README
    "rule_score",
    "execution_score",  # nullable: null for open/not-yet-closed trades
    "confidence",
    "hist_win_rate_all",
    "hist_win_rate_pair",
    "hist_avg_rr_all",
    "hist_streak_dir",
    "hist_rule_score_ema10",
    "hist_execution_score_ema10",
    "hist_strategy_health_score",  # "Strategy Health" — added below
]

FEATURE_COLUMNS = CATEGORICAL_FEATURES + NUMERIC_FEATURES
TARGET_COLUMN = "y_win"

#: Sentinel date guaranteed to sort after any real trade date (plain
#: "YYYY-MM-DD" strings), used only to make a hypothetical "next trade"
#: land last when run back through Sprint 6's ``build_dataset`` — see
#: ``historical_features_for_candidate`` below.
_FUTURE_SENTINEL_DATE = "9999-12-31"
_CANDIDATE_ID = "__sprint7_candidate__"


def _row_to_health_entry(row: dict[str, Any]) -> dict[str, Any]:
    """Adapts one flattened (snake_case) ML row back into the shape
    ``compute_strategy_health`` (Sprint 6, camelCase) expects. No
    Sprint 6 code changes — just a field-name bridge."""
    return {
        "rulesFollowed": row.get("rules_followed"),
        "followedPlan": row.get("followed_plan"),
        "executionScore": row.get("execution_score"),
        "rr": row.get("rr"),
        "sl": row.get("stop_loss"),
        "emotion": row.get("emotion"),
        "exitReason": row.get("exit_reason"),
        "pnl": row.get("pnl"),
        "date": row.get("date"),
    }


def add_hist_strategy_health(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """add_hist_strategy_health(rows) -> new list of new dicts (does
    **not** mutate ``rows`` or the dicts inside it — found during the
    audit that the original version mutated its input in place, a
    surprising side effect for a function that looks read-only from the
    caller's side, e.g. ``prepare_training_data()`` passing in the
    caller's own ``valid_rows`` list). ``rows`` must already be
    chronologically ordered, as produced by ``build_dataset``.

    Adds a ``hist_strategy_health_score`` key: the Strategy Health
    engine's overall score computed using only rows strictly before the
    current one. The first rows (before there's any history) get
    ``None``, matching the null-until-enough-history convention every
    other ``hist_*`` column already uses."""
    prior: list[dict[str, Any]] = []
    result: list[dict[str, Any]] = []
    for row in rows:
        health = compute_strategy_health([_row_to_health_entry(r) for r in prior]) if prior else None
        new_row = {**row, "hist_strategy_health_score": health["healthScore"] if health else None}
        result.append(new_row)
        prior.append(row)
    return result


def historical_strategy_health_for_candidate(rows: list[dict[str, Any]]) -> float | None:
    """The Strategy Health score computed from *all* of the user's
    current rows, i.e. "as of right now" — used when scoring a
    hypothetical trade that hasn't been logged yet (Phase 5)."""
    if not rows:
        return None
    health = compute_strategy_health([_row_to_health_entry(r) for r in rows])
    return health["healthScore"] if health else None


def historical_features_for_candidate(
    entries: list[dict[str, Any]], candidate: dict[str, Any]
) -> dict[str, Any]:
    """historical_features_for_candidate(entries, candidate) — computes
    the six Sprint-6-defined ``hist_*`` rolling columns
    (``hist_win_rate_all``, ``hist_win_rate_pair``, ``hist_avg_rr_all``,
    ``hist_streak_dir``, ``hist_rule_score_ema10``,
    ``hist_execution_score_ema10``) for a trade that **hasn't happened
    yet**, by reusing Sprint 6's own ``build_dataset()`` rather than
    re-deriving the same formulas a second time (which would risk
    train/predict skew if the two implementations ever drifted apart).

    Trick: append one synthetic "next" entry (dated far in the future
    so it always sorts last) carrying only the candidate's ``pair``/
    ``session``, run the *real* trade history plus this one synthetic
    entry through ``build_dataset()``, and read the ``hist_*`` columns
    off the last (synthetic) row — those are, by construction, computed
    from only the real, already-logged trades.
    """
    synthetic = {
        "id": _CANDIDATE_ID,
        "date": _FUTURE_SENTINEL_DATE,
        "pair": candidate.get("pair"),
        "session": candidate.get("session"),
    }
    rows = build_dataset(list(entries) + [synthetic], user_id=candidate.get("user_id", 1))
    last = rows[-1] if rows else {}
    return {
        "hist_win_rate_all": last.get("hist_win_rate_all"),
        "hist_win_rate_pair": last.get("hist_win_rate_pair"),
        "hist_avg_rr_all": last.get("hist_avg_rr_all"),
        "hist_streak_dir": last.get("hist_streak_dir"),
        "hist_rule_score_ema10": last.get("hist_rule_score_ema10"),
        "hist_execution_score_ema10": last.get("hist_execution_score_ema10"),
    }


def build_preprocessor() -> ColumnTransformer:
    """build_preprocessor() — the encoding/scaling half of the model
    pipeline. Missing categoricals become an explicit ``"missing"``
    category (rather than crashing); missing numerics are median-imputed
    then standardized. ``handle_unknown="ignore"`` on the one-hot
    encoder means a pair/session/etc. never seen during training won't
    crash prediction — it just contributes an all-zero row for that
    feature instead of a hard error."""
    categorical_pipeline = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="constant", fill_value="missing")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    numeric_pipeline = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("cat", categorical_pipeline, CATEGORICAL_FEATURES),
            ("num", numeric_pipeline, NUMERIC_FEATURES),
        ]
    )


def rows_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """rows_to_frame(rows) — projects flattened ML rows down to exactly
    ``FEATURE_COLUMNS``, in order, adding any missing column as all-NaN
    so ``build_preprocessor()``'s imputers can fill it in."""
    frame = pd.DataFrame(rows)
    for col in FEATURE_COLUMNS:
        if col not in frame.columns:
            frame[col] = None
    return frame[FEATURE_COLUMNS]


def prepare_training_data(rows: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.Series]:
    """prepare_training_data(valid_rows) -> (X, y). ``rows`` must already
    be chronologically ordered (as returned by ``build_dataset``) and
    pre-filtered to ``validation_status == "valid"`` — Phase 1's job,
    not this function's."""
    rows = add_hist_strategy_health(list(rows))
    X = rows_to_frame(rows)
    y = pd.Series([int(row.get("y_win") or 0) for row in rows], name=TARGET_COLUMN)
    return X, y


def prepare_candidate_row(
    entries: list[dict[str, Any]], candidate: dict[str, Any]
) -> pd.DataFrame:
    """prepare_candidate_row(entries, candidate) — builds the one-row
    feature frame for a not-yet-logged trade, for Phase 5's prediction
    endpoint. ``entries`` is the user's full existing trade history
    (camelCase engine dicts, as returned by ``Trade.to_engine_dict()``);
    ``candidate`` is the new trade's own fields (see
    ``app/schemas/ml_training.py::PredictionRequest``).
    """
    hist = historical_features_for_candidate(entries, candidate)
    row = {
        "pair": (candidate.get("pair") or "").upper() or None,
        "asset": candidate.get("asset"),
        "direction": candidate.get("direction"),
        "session": candidate.get("session"),
        "h4_trend": candidate.get("h4_trend"),
        "h4_poi_type": candidate.get("h4_poi_type"),
        "emotion": candidate.get("emotion"),
        "has_bos": 1 if candidate.get("has_bos") else 0,
        "has_choch": 1 if candidate.get("has_choch") else 0,
        "has_liquidity_sweep": 1 if candidate.get("has_liquidity_sweep") else 0,
        "planned_rr": candidate.get("planned_rr"),
        "rule_score": candidate.get("rule_score"),
        "execution_score": candidate.get("execution_score"),
        "confidence": candidate.get("confidence"),
        **hist,
        "hist_strategy_health_score": historical_strategy_health_for_candidate(entries),
    }
    return rows_to_frame([row])
