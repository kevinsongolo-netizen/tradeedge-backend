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
from app.ml.persistence import load_model


class NoActiveModelError(NotFoundError):
    """Raised when a user calls ``/ml/predict`` before ever training a
    model (``POST /ml/train``). Subclasses ``app.errors.NotFoundError``
    so it's automatically rendered as a 404 by the global handler."""

    code = "NO_ACTIVE_MODEL"


# In-process cache: (user_id, file_path) -> loaded joblib artifact.
# Found during the audit: MLPredictionService.predict() was calling
# joblib.load() from disk on *every single* prediction request, even
# though the active model rarely changes (only on a new POST
# /ml/train). Keyed by file_path (which is unique per version — see
# app/ml/persistence.py::model_filename), so training a new version
# naturally produces a cache miss and loads the new file; nothing needs
# explicit invalidation. Same caveat as the rest of this app's
# in-process caches (FingerprintCache/TTLCache in
# app/services/cache.py): per-process only, not shared across multiple
# uvicorn workers.
_MODEL_CACHE: dict[tuple[int, str], Any] = {}


async def _load_cached_model(user_id: int, file_path: str) -> Any:
    key = (user_id, file_path)
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached
    # joblib.load() deserializes a scikit-learn Pipeline from disk —
    # blocking I/O + CPU work. Offloaded to a worker thread so it never
    # blocks the event loop, same reasoning as train_and_compare() in
    # ml_training_service.py.
    artifact = await asyncio.to_thread(load_model, Path(file_path))
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
        if active is None or not active.file_path:
            raise NoActiveModelError(
                "No trained model found for this user yet. Call POST /api/v1/ml/train first."
            )

        pipeline = await _load_cached_model(user_id, active.file_path)

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
