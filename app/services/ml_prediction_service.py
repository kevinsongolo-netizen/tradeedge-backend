"""Sprint 7 Phase 5 — Prediction service.

Loads the current user's active persisted model and scores a candidate
trade — logged or not-yet-logged — using the user's real trade history
for the historical/rolling features (never zeros or global defaults).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.ml_model_repo import MLModelRepository
from app.db.repositories.trade_repo import TradeRepository
from app.engines.ml_dataset import _quality_bucket
from app.errors import NotFoundError
from app.ml.features import prepare_candidate_row
from app.ml.persistence import load_model, load_model_bytes


class NoActiveModelError(NotFoundError):
    """Raised when a user calls ``/ml/predict`` before ever training a
    model (``POST /ml/train``). Subclasses ``app.errors.NotFoundError``
    so it's automatically rendered as a 404 by the global handler."""

    code = "NO_ACTIVE_MODEL"


# In-process cache: (user_id, version) -> loaded joblib artifact.
# Found during the audit: MLPredictionService.predict() was calling
# joblib.load() from disk on *every single* prediction request, even
# though the active model rarely changes (only on a new POST
# /ml/train). Keyed by version (unique per user -- see
# app/ml/persistence.py::next_version), so training a new version
# naturally produces a cache miss and loads the new one; nothing needs
# explicit invalidation. Same caveat as the rest of this app's
# in-process caches (FingerprintCache/TTLCache in
# app/services/cache.py): per-process only, not shared across multiple
# uvicorn workers, and cleared on every restart -- which is exactly why
# the DB-blob fallback below matters.
_MODEL_CACHE: dict[tuple[int, str], Any] = {}


async def _load_cached_model(user_id: int, model_row: Any) -> Any:
    """Loads the fitted pipeline for ``model_row`` (an ``MLModel`` DB
    row), preferring the on-disk file (fast, no DB payload to
    deserialize-of-a-deserialize) but falling back to the model bytes
    stored on the row itself if the file is missing.

    That fallback is the real fix for a production bug: Render's free
    tier has no persistent disk, so the joblib file written by
    ``POST /ml/train`` is wiped the next time the service spins down
    and restarts (which happens after ~15 minutes idle). The DB row
    survives that restart (Postgres is a separate, persistent service),
    so without this fallback every prediction crashed with
    FileNotFoundError as soon as the container recycled -- even though
    the app considered a model "active"."""
    key = (user_id, model_row.version)
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached
    # joblib.load()/loads() deserializes a scikit-learn Pipeline --
    # blocking I/O + CPU work. Offloaded to a worker thread so it never
    # blocks the event loop, same reasoning as train_and_compare() in
    # ml_training_service.py.
    try:
        artifact = await asyncio.to_thread(load_model, Path(model_row.file_path))
    except (FileNotFoundError, TypeError):
        if not model_row.model_blob:
            raise
        artifact = await asyncio.to_thread(load_model_bytes, model_row.model_blob)
    pipeline = artifact["pipeline"]
    _MODEL_CACHE[key] = pipeline
    return pipeline


class MLPredictionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.model_repo = MLModelRepository(session)
        self.trade_repo = TradeRepository(session)

    async def predict(self, user_id: int, candidate: dict[str, Any]) -> dict[str, Any]:
        active = await self.model_repo.get_active(user_id)
        if active is None or not (active.file_path or active.model_blob):
            raise NoActiveModelError(
                "No trained model found for this user yet. Call POST /api/v1/ml/train first."
            )

        pipeline = await _load_cached_model(user_id, active)

        trades = await self.trade_repo.list_all_with_analyses(user_id)
        entries = [t.to_engine_dict() for t in trades]

        candidate_with_user = {**candidate, "user_id": user_id}
        X = prepare_candidate_row(entries, candidate_with_user)
        win_probability = float(pipeline.predict_proba(X)[0, 1])
        quality_score = round(win_probability * 100, 2)

        return {
            "winProbability": round(win_probability, 4),
            "predictedQualityScore": quality_score,
            # Reuses Sprint 6's bucket thresholds (app/engines/ml_dataset.py)
            # instead of re-declaring the same 90/80/70 cutoffs a second
            # time — found duplicated during the audit.
            "predictedQualityBucket": _quality_bucket(quality_score),
            "modelVersion": active.version,
            "algorithm": active.algorithm,
        }
