"""Chart Analysis Engine router (Sprint 10; rewritten Sprint 20).

* ``POST /chart/analyze-candles`` / ``POST /chart/analyze-image`` —
  Level 1 only (structured chart read, no verdict of any kind). Kept
  as small generic utilities.
* ``POST /chart/full-analysis/image`` — the screenshot-first workflow's
  one call since Sprint 20: reads the screenshot (pair, timeframe,
  entry/SL/TP/R:R, POI/BOS/CHoCH labels -- whatever the trader's own
  MT5 indicator and order panel already show), then compares that
  setup against the trader's own trade history via weighted similarity
  (``app/engines/setup_insight_engine.py``). Returns the extracted
  setup + a plain-language insight -- never a VALID/INVALID/TAKE/WAIT
  verdict. That decision stays with the trader.

The old Level 2 (rule validation)/Level 3 (rule narration) endpoints
(``/validate``, ``/coach``, ``/full-analysis/candles``) are retired
along with the rule engines they depended on -- see ``app/_legacy/``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.deps import get_current_user_id
from app.errors import ValidationError
from app.schemas.chart import (
    CandlesAnalyzeRequest,
    ChartAnalysis,
    ChartAnalysisResponse,
    ChartSetupInsightResponse,
    ScreenshotUploadResult,
    SetupExtraction,
    SetupInsight,
)
from app.services.chart_service import ChartService

router = APIRouter(prefix="/chart", tags=["chart"])

MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8MB — generous for a chart screenshot, cheap to validate up front
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}


@router.post(
    "/analyze-candles",
    response_model=ChartAnalysisResponse,
    summary="Level 1 — deterministic SMC read from real OHLC candle data",
)
async def analyze_candles(body: CandlesAnalyzeRequest) -> ChartAnalysisResponse:
    service = ChartService()
    candles = [c.model_dump(by_alias=False) for c in body.candles]
    analysis_dict = await service.analyze_candles(candles)
    return ChartAnalysisResponse(analysis=ChartAnalysis(**analysis_dict))


@router.post(
    "/analyze-image",
    response_model=ChartAnalysisResponse,
    summary="Level 1 — best-effort SMC read from a chart screenshot (vision AI)",
)
async def analyze_image(file: UploadFile = File(...)) -> ChartAnalysisResponse:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError(f"Unsupported image type: {file.content_type}. Use PNG, JPEG, or WEBP.")
    image_bytes = await file.read()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValidationError("Image too large — please upload a screenshot under 8MB.")
    service = ChartService()
    analysis_dict, meta = await service.analyze_image(image_bytes, file.content_type)
    return ChartAnalysisResponse(analysis=ChartAnalysis(**analysis_dict), meta=meta)


@router.post(
    "/full-analysis/image",
    response_model=ChartSetupInsightResponse,
    summary="Screenshot-first workflow — read the setup, compare it against your own trade history",
)
async def full_analysis_image(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> ChartSetupInsightResponse:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError(f"Unsupported image type: {file.content_type}. Use PNG, JPEG, or WEBP.")
    image_bytes = await file.read()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValidationError("Image too large — please upload a screenshot under 8MB.")
    service = ChartService(session)
    result = await service.full_analysis_from_image(image_bytes, file.content_type, user_id=user_id)
    return ChartSetupInsightResponse(
        extraction=SetupExtraction(**result["extraction"]),
        insight=SetupInsight(**result["insight"]),
        meta=result["meta"],
        fingerprint=result.get("fingerprint"),
    )


@router.post(
    "/upload-screenshot",
    response_model=ScreenshotUploadResult,
    summary="Sprint 20 Phase 3 — save a screenshot with no vision analysis (e.g. an after-exit chart shot)",
)
async def upload_screenshot(file: UploadFile = File(...)) -> ScreenshotUploadResult:
    """No vision read, no history comparison -- just permanent storage
    for a screenshot the trader wants attached to an already-logged
    trade (typically "how it actually played out" after closing).
    Never errors out on a storage failure -- returns ``url=None`` with
    the reason instead, since a screenshot save failing shouldn't block
    anything else the trader is doing."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError(f"Unsupported image type: {file.content_type}. Use PNG, JPEG, or WEBP.")
    image_bytes = await file.read()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValidationError("Image too large — please upload a screenshot under 8MB.")
    service = ChartService()
    result = await service.upload_screenshot(image_bytes, file.content_type)
    return ScreenshotUploadResult(**result)
