"""Sprint 7 Phase 6 — Model persistence (joblib) + versioning.

One joblib file per trained model version, containing the fitted
scikit-learn ``Pipeline`` (preprocessing + classifier together — see
``app/ml/features.py::build_preprocessor``) plus enough metadata to be
useful without a DB round-trip. The ``ml_models`` DB table (Sprint 6
placeholder, ``app/db/models/ml_export.py::MLModel``) is the source of
truth for *which* version is active; this module only reads/writes the
on-disk artifact a given row points to.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib


def next_version(existing_versions: list[str]) -> str:
    """next_version(["v1", "v2"]) -> "v3". Versions are simple
    incrementing integers prefixed with "v" — enough for a single-user
    local app; not a semantic-versioning scheme."""
    numbers = []
    for v in existing_versions:
        if v.startswith("v") and v[1:].isdigit():
            numbers.append(int(v[1:]))
    return f"v{(max(numbers) + 1) if numbers else 1}"


def model_filename(user_id: int, version: str) -> str:
    return f"tradeedge_ml_user{user_id}_{version}.joblib"


def save_model(path: Path, pipeline: Any, metadata: dict[str, Any]) -> None:
    """save_model(path, pipeline, metadata) — writes one joblib artifact
    containing both the fitted pipeline and its metadata (algorithm,
    version, metrics, feature columns, trained_at) so the file is
    self-describing even without the DB row."""
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": pipeline, "metadata": metadata}, path)


def load_model(path: Path) -> dict[str, Any]:
    """load_model(path) -> {"pipeline": ..., "metadata": {...}}."""
    if not path.exists():
        raise FileNotFoundError(f"No model artifact at {path}")
    return joblib.load(path)
