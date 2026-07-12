"""Sprint 7 router — dataset validation report, training, model
registry, and prediction (``/api/v1/ml/*``).

New file, mounted alongside Sprint 6's ``app/api/v1/ml.py`` (same
``/ml`` prefix, disjoint paths) — Sprint 6's ``/ml/dataset``,
``/ml/validate``, ``/ml/exports`` endpoints are untouched.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.deps import get_current_user_id
from app.schemas.ml_training import (
    DatasetValidationReport,
    ModelInfo,
    PredictionRequest,
    PredictionResult,
    TrainingRequest,
    TrainingResult,
)
from app.services.ml_prediction_service import MLPredictionService
from app.services.ml_training_service import MLTrainingService

router = APIRouter(prefix="/ml", tags=["ml-training"])


@router.get(
    "/dataset/validation-report",
    response_model=DatasetValidationReport,
    summary="Phase 1 — dataset validation report (does not train anything)",
)
async def get_validation_report(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> DatasetValidationReport:
    service = MLTrainingService(session)
    report = await service.validation_report(user_id)
    return DatasetValidationReport(**report)


@router.post(
    "/train",
    response_model=TrainingResult,
    summary="Train, compare, and persist the best model (Phases 3/4/6)",
)
async def train_model(
    body: TrainingRequest,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> TrainingResult:
    """Runs Phase 1's gate first (raises 422 if the dataset isn't ready
    — see ``GET /ml/dataset/validation-report`` for why), then Phase
    2 (feature engineering), Phase 3 (train/val/test split), Phase 4
    (train + compare Logistic Regression / Random Forest / Gradient
    Boosting, pick the best on validation, report final metrics on a
    held-out test set), and Phase 6 (persist the winner, activate it as
    the new latest version).
    """
    service = MLTrainingService(session)
    result = await service.train(user_id)
    return TrainingResult(**result)


@router.get(
    "/models",
    response_model=list[ModelInfo],
    summary="List all trained model versions for this user",
)
async def list_models(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> list[ModelInfo]:
    service = MLTrainingService(session)
    models = await service.list_models(user_id)
    return [ModelInfo(**m) for m in models]


@router.get(
    "/models/active",
    response_model=ModelInfo,
    summary="Load the latest (active) trained model's info",
)
async def get_active_model(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> ModelInfo:
    from app.errors import NotFoundError

    service = MLTrainingService(session)
    active = await service.active_model(user_id)
    if active is None:
        raise NotFoundError(
            "No trained model yet for this user. Call POST /api/v1/ml/train first.",
        )
    return ModelInfo(**active)


@router.post(
    "/predict",
    response_model=PredictionResult,
    summary="Predict win probability / quality for a trade using the active model",
)
async def predict_trade(
    body: PredictionRequest,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> PredictionResult:
    """Scores a candidate trade — already logged or hypothetical — with
    the user's currently active model. Historical/rolling features are
    computed from the user's *real* trade history, not supplied by the
    caller, so the same setup fields can predict differently for two
    different users (or for the same user at two different points in
    their trading history)."""
    service = MLPredictionService(session)
    result = await service.predict(user_id, body.model_dump(by_alias=False))
    return PredictionResult(**result)
