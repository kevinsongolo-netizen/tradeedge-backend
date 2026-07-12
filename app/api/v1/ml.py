"""ML dataset router — ``/api/v1/ml/*`` (Section 4.7).

Every exported record includes trade info, strategy/setup info, AI
scores, leakage-safe historical statistics, validation status, and
outcome (Section 8) — directly usable by Python/scikit-learn.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.deps import get_current_user_id
from app.engines.ml_dataset import ML_DATASET_VERSION
from app.schemas.ml import MlExportRequest, MlExportResult, MlValidationReport
from app.services.ml_service import MLService

router = APIRouter(prefix="/ml", tags=["ml"])


@router.get("/dataset", summary="Export the ML training dataset")
async def get_dataset(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
):
    """Returns validated rows only, in the exact ML schema (Section 8).
    ``format=csv`` streams ``text/csv`` with the fixed column order;
    ``format=json`` returns a JSON array."""
    service = MLService(session)
    if format == "csv":
        content = await service.dataset_csv(user_id, valid_only=True)
        stamp = datetime.now(timezone.utc).date().isoformat()
        filename = f"tradeedge-ml-dataset-{stamp}-v{ML_DATASET_VERSION}.csv"
        return PlainTextResponse(
            content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    rows = await service.dataset_json(user_id, valid_only=True)
    return JSONResponse(content=rows)


@router.get("/validate", response_model=MlValidationReport, summary="Validate the dataset without exporting")
async def validate_dataset(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> MlValidationReport:
    service = MLService(session)
    report = await service.validate(user_id)
    return MlValidationReport(**report)


@router.post("/exports", response_model=MlExportResult, summary="Write JSON/CSV export to disk")
async def create_export(
    body: MlExportRequest,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> MlExportResult:
    """Writes the artifact(s) to ``EXPORT_DIR`` and records an audit row
    in ``ml_exports`` (Section 9.5) so a Sprint 7 training run can be
    reproduced exactly."""
    service = MLService(session)
    result = await service.export(user_id, body.format)
    return MlExportResult(**result)
