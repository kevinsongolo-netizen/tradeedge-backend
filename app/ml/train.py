"""Sprint 7 Phase 3/4 — Training pipeline + model comparison.

Trains Logistic Regression, Random Forest, and Gradient Boosting
classifiers on the same train split, compares them on a held-out
validation split (accuracy/precision/recall/F1/ROC AUC), picks the best
one, refits it on train+validation, and reports final metrics on a
held-out test split it has never seen — so the reported numbers aren't
inflated by the same data used to pick the winner (Phase 4's "do not
overfit").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from app.errors import ValidationError
from app.ml.features import build_preprocessor

RANDOM_STATE = 42
TEST_FRACTION = 0.2
VAL_FRACTION = 0.2  # of the remaining (train+val) portion, i.e. 20% of the whole set


class InsufficientDataError(ValidationError):
    """Raised when there aren't enough valid, labeled trades to train
    or evaluate a model without the result being meaningless. Subclasses
    ``app.errors.ValidationError`` so the global exception handler
    (Section 11) turns it into the standard 422 envelope automatically
    — routers don't need their own try/except for this."""

    code = "INSUFFICIENT_TRAINING_DATA"


def _candidate_models() -> dict[str, Any]:
    """Fresh, unfitted estimator instances — small/regularized on
    purpose (shallow trees, L2 penalty, balanced class weights) since
    personal trading journals are small datasets where an
    unconstrained model would just memorize the training rows."""
    return {
        "logistic_regression": LogisticRegression(
            max_iter=1000, class_weight="balanced", random_state=RANDOM_STATE
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=200,
            max_depth=6,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=RANDOM_STATE,
        ),
        "gradient_boosting": GradientBoostingClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.05,
            random_state=RANDOM_STATE,
        ),
    }


def _can_stratify(y: pd.Series, n_splits_needed: int = 2) -> bool:
    counts = y.value_counts()
    return len(counts) >= 2 and counts.min() >= n_splits_needed


def split_dataset(
    X: pd.DataFrame, y: pd.Series
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """split_dataset(X, y) -> (X_train, X_val, X_test, y_train, y_val, y_test).

    Stratifies on the target when both classes have enough members;
    falls back to a plain random split otherwise (e.g. a brand-new
    journal that's all wins or all losses so far) rather than crashing.
    """
    stratify = y if _can_stratify(y) else None
    X_temp, X_test, y_temp, y_test = train_test_split(
        X, y, test_size=TEST_FRACTION, random_state=RANDOM_STATE, stratify=stratify
    )
    stratify_temp = y_temp if _can_stratify(y_temp) else None
    X_train, X_val, y_train, y_val = train_test_split(
        X_temp, y_temp, test_size=VAL_FRACTION, random_state=RANDOM_STATE, stratify=stratify_temp
    )
    return X_train, X_val, X_test, y_train, y_val, y_test


def _safe_roc_auc(y_true: pd.Series, y_proba: np.ndarray) -> float | None:
    if len(set(y_true)) < 2:
        return None
    try:
        return float(roc_auc_score(y_true, y_proba))
    except ValueError:
        return None


def compute_metrics(y_true: pd.Series, y_pred: np.ndarray, y_proba: np.ndarray) -> dict[str, float | None]:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "rocAuc": _safe_roc_auc(y_true, y_proba),
    }


def _fit_and_score(estimator: Any, X_train, y_train, X_eval, y_eval) -> tuple[Pipeline, dict]:
    pipeline = Pipeline(steps=[("preprocess", build_preprocessor()), ("model", estimator)])
    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_eval)
    y_proba = pipeline.predict_proba(X_eval)[:, 1]
    return pipeline, compute_metrics(y_eval, y_pred, y_proba)


@dataclass
class TrainingOutcome:
    algorithm: str
    pipeline: Pipeline
    val_metrics: dict
    test_metrics: dict
    train_metrics: dict
    candidates: dict[str, dict] = field(default_factory=dict)
    overfit_warning: bool = False
    rows_used: int = 0
    split_sizes: dict[str, int] = field(default_factory=dict)


#: If train-set accuracy beats test-set accuracy by more than this,
#: flag a possible-overfitting warning in the result (still persisted —
#: it's a diagnostic, not a hard failure — but callers/docs should be
#: cautious about trusting the model until more data accumulates).
OVERFIT_ACCURACY_GAP = 0.25

MIN_ROWS_FOR_SPLIT = 15  # need at least a handful of rows in each of train/val/test


def train_and_compare(X: pd.DataFrame, y: pd.Series) -> TrainingOutcome:
    """train_and_compare(X, y) — Phase 3 (split) + Phase 4 (compare +
    select). Raises ``InsufficientDataError`` if there isn't enough
    data for a meaningful three-way split."""
    if len(X) < MIN_ROWS_FOR_SPLIT:
        raise InsufficientDataError(
            f"Need at least {MIN_ROWS_FOR_SPLIT} valid trades to train/validate/test a "
            f"model; have {len(X)}."
        )

    X_train, X_val, X_test, y_train, y_val, y_test = split_dataset(X, y)

    candidates: dict[str, dict] = {}
    fitted: dict[str, Pipeline] = {}
    for name, estimator in _candidate_models().items():
        pipeline, val_metrics = _fit_and_score(estimator, X_train, y_train, X_val, y_val)
        candidates[name] = val_metrics
        fitted[name] = pipeline

    def selection_key(name: str) -> tuple[float, float]:
        m = candidates[name]
        # Prefer ROC AUC when available (threshold-independent); fall
        # back to F1 if the validation split only has one class.
        return (m["rocAuc"] if m["rocAuc"] is not None else -1.0, m["f1"])

    best_name = max(candidates, key=selection_key)

    # Refit the winning algorithm on train+validation combined, then
    # report final metrics on the untouched test split (Phase 4's
    # "compare" happens on validation; the number we report and persist
    # comes from data the winner never influenced its own selection with).
    X_train_full = pd.concat([X_train, X_val])
    y_train_full = pd.concat([y_train, y_val])
    final_pipeline, test_metrics = _fit_and_score(
        _candidate_models()[best_name], X_train_full, y_train_full, X_test, y_test
    )
    _, train_metrics = _fit_and_score(
        _candidate_models()[best_name], X_train_full, y_train_full, X_train_full, y_train_full
    )

    overfit_warning = (train_metrics["accuracy"] - test_metrics["accuracy"]) > OVERFIT_ACCURACY_GAP

    return TrainingOutcome(
        algorithm=best_name,
        pipeline=final_pipeline,
        val_metrics=candidates[best_name],
        test_metrics=test_metrics,
        train_metrics=train_metrics,
        candidates=candidates,
        overfit_warning=overfit_warning,
        rows_used=len(X),
        split_sizes={"train": len(X_train), "val": len(X_val), "test": len(X_test)},
    )
