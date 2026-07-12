"""Sprint 7 — Training service.

Orchestrates Phase 1 (validation), Phase 2/3/4 (features + train +
compare), and Phase 6 (persistence + versioning) behind the
``/api/v1/ml/train`` and ``/api/v1/ml/models*`` endpoints. Reuses
Sprint 6's ``MLService.build()`` for the raw flattened dataset rather
than re-querying the DB itself.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.repositories.ml_model_repo import MLModelRepository
from app.errors import ConflictError
from app.ml.dataset_validation import generate_validation_report
from app.ml.features import FEATURE_COLUMNS, prepare_training_data
from app.ml.persistence import model_filename, next_version, save_model
from app.ml.train import InsufficientDataError, train_and_compare
from app.services.ml_service import MLService

__all__ = ["MLTrainingService", "InsufficientDataError"]


class MLTrainingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.ml_service = MLService(session)
        self.model_repo = MLModelRepository(session)
        self.settings = get_settings()

    async def validation_report(self, user_id: int) -> dict[str, Any]:
        """Phase 1 — ``GET /ml/dataset/validation-report``. Never trains
        anything; read-only."""
        rows = await self.ml_service.build(user_id)
        return generate_validation_report(rows)

    async def train(self, user_id: int) -> dict[str, Any]:
        """Phase 3/4/6 — ``POST /ml/train``. Raises
        ``InsufficientDataError`` (mapped to HTTP 422 by the router) if
        Phase 1's gate isn't satisfied; never trains on an invalid or
        too-small dataset."""
        rows = await self.ml_service.build(user_id)
        report = generate_validation_report(rows)
        if not report["readyForTraining"]:
            raise InsufficientDataError(report["reason"] or "Dataset is not ready for training.")

        valid_rows = [r for r in rows if r["validation_status"] == "valid"]
        X, y = prepare_training_data(valid_rows)
        # train_and_compare() fits three scikit-learn models — genuinely
        # CPU-bound, synchronous work that can take seconds. Running it
        # directly in this async method would block the entire event
        # loop (and every other in-flight request, including /healthz)
        # for the duration. asyncio.to_thread() runs it on FastAPI's
        # worker thread pool instead, found during the production
        # readiness audit after a 40-row training run measured at 3.4s
        # of wall-clock time spent entirely on the event loop thread.
        outcome = await asyncio.to_thread(train_and_compare, X, y)

        existing = await self.model_repo.list_all(user_id)
        version = next_version([m.version for m in existing])
        trained_at = datetime.now(timezone.utc)

        models_dir = Path(self.settings.models_dir)
        path = models_dir / model_filename(user_id, version)
        metadata = {
            "algorithm": outcome.algorithm,
            "version": version,
            "trainedAt": trained_at.isoformat(),
            "trainingRows": outcome.rows_used,
            "featureColumns": FEATURE_COLUMNS,
            "candidates": outcome.candidates,
            "valMetrics": outcome.val_metrics,
            "testMetrics": outcome.test_metrics,
            "trainMetrics": outcome.train_metrics,
            "splitSizes": outcome.split_sizes,
            "overfitWarning": outcome.overfit_warning,
        }
        save_model(path, outcome.pipeline, metadata)

        try:
            await self.model_repo.insert_and_activate(
                user_id,
                {
                    "version": version,
                    "algorithm": outcome.algorithm,
                    "trained_at": trained_at,
                    "training_rows": outcome.rows_used,
                    "metrics_json": {
                        "candidates": outcome.candidates,
                        "valMetrics": outcome.val_metrics,
                        "testMetrics": outcome.test_metrics,
                        "trainMetrics": outcome.train_metrics,
                        "splitSizes": outcome.split_sizes,
                        "overfitWarning": outcome.overfit_warning,
                    },
                    "file_path": str(path),
                },
            )
            await self.session.commit()
        except IntegrityError:
            # Found during the audit: two concurrent POST /ml/train
            # calls for the same user could both compute the same
            # "next version" string (migration 0002 added a DB-level
            # unique constraint on (user_id, version) plus a partial
            # unique index enforcing at most one active row per user,
            # specifically to catch this). Roll back and surface a
            # clean 409 instead of a raw 500 or, worse, a silently
            # corrupted "two active models" state.
            await self.session.rollback()
            raise ConflictError(
                "Another training run for this user just completed — retry."
            ) from None

        return {
            "version": version,
            "algorithm": outcome.algorithm,
            "rowsUsed": outcome.rows_used,
            "splitSizes": outcome.split_sizes,
            "candidates": outcome.candidates,
            "valMetrics": outcome.val_metrics,
            "testMetrics": outcome.test_metrics,
            "trainMetrics": outcome.train_metrics,
            "overfitWarning": outcome.overfit_warning,
            "trainedAt": trained_at.isoformat(),
            "modelPath": str(path),
        }

    async def list_models(self, user_id: int) -> list[dict[str, Any]]:
        rows = await self.model_repo.list_all(user_id)
        return [_model_to_info(m) for m in rows]

    async def active_model(self, user_id: int) -> dict[str, Any] | None:
        row = await self.model_repo.get_active(user_id)
        return _model_to_info(row) if row else None


def _model_to_info(model: Any) -> dict[str, Any]:
    return {
        "id": model.id,
        "version": model.version,
        "algorithm": model.algorithm,
        "trainedAt": model.trained_at.isoformat() if model.trained_at else None,
        "trainingRows": model.training_rows,
        "metrics": model.metrics_json,
        "isActive": model.is_active,
        "filePath": model.file_path,
    }
