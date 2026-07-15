"""Sprint 10 — Chart Analysis Engine router.

Three levels, two Level-1 reading paths:

* ``POST /chart/analyze-candles`` / ``POST /chart/analyze-image`` —
  Level 1 only (structured chart read).
* ``POST /chart/validate`` — Level 2 (trade validation) given an
  already-produced ``ChartAnalysis``.
* ``POST /chart/coach`` — Level 3 (AI coach explanation + confidence
  breakdown) given an analysis + its validation result.
* ``POST /chart/full-analysis/candles`` and
  ``POST /chart/full-analysis/image`` — all three levels in one round
  trip, which is what the UI calls for the common case.

No database/auth dependency — chart analyses are stateless in this
first cut (see ``app/services/chart_service.py``).
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile

from app.errors import ValidationError
from app.schemas.chart import (
    CandlesAnalyzeRequest,
    ChartAnalysis,
    ChartAnalysisResponse,
    CoachExplanationResult,
    CoachRequest,
    FullCandlesAnalysisRequest,
    FullChartAnalysisResponse,
    MultiTimeframeConfirmation,
    TradeValidationRequest,
    TradeValidationResult,
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
    "/validate",
    response_model=TradeValidationResult,
    summary="Level 2 — validate a Level-1 analysis against SMC trading rules",
)
async def validate(body: TradeValidationRequest) -> TradeValidationResult:
    service = ChartService()
    result = service.validate(
        body.analysis,
        direction=body.direction,
        planned_rr=body.planned_rr,
        has_m15_bos=body.has_m15_bos,
        has_m15_choch=body.has_m15_choch,
        has_m15_entry_confirmation=body.has_m15_entry_confirmation,
        has_liquidity_sweep=body.has_liquidity_sweep,
        min_rr=body.min_rr,
    )
    return TradeValidationResult(**result)


@router.post(
    "/coach",
    response_model=CoachExplanationResult,
    summary="Level 3 — plain-language AI coach explanation + confidence breakdown",
)
async def coach(body: CoachRequest) -> CoachExplanationResult:
    service = ChartService()
    result = service.coach(body.analysis, body.validation.model_dump(by_alias=True), body.min_rr)
    return CoachExplanationResult(**result)


@router.post(
    "/full-analysis/candles",
    response_model=FullChartAnalysisResponse,
    summary="Levels 1 + 2 + 3 in one call, from real OHLC candle data",
)
async def full_analysis_candles(body: FullCandlesAnalysisRequest) -> FullChartAnalysisResponse:
    service = ChartService()
    candles = [c.model_dump(by_alias=False) for c in body.candles]
    m15_candles = (
        [c.model_dump(by_alias=False) for c in body.m15_candles] if body.m15_candles else None
    )
    daily_candles = (
        [c.model_dump(by_alias=False) for c in body.daily_candles] if body.daily_candles else None
    )
    result = await service.full_analysis_from_candles(
        candles,
        direction=body.direction,
        planned_rr=body.planned_rr,
        has_m15_bos=body.has_m15_bos,
        has_m15_choch=body.has_m15_choch,
        has_m15_entry_confirmation=body.has_m15_entry_confirmation,
        has_liquidity_sweep=body.has_liquidity_sweep,
        min_rr=body.min_rr,
        m15_candles=m15_candles,
        daily_candles=daily_candles,
        open_trade_in_loss=body.open_trade_in_loss,
    )
    multi_timeframe = result.get("multi_timeframe")
    return FullChartAnalysisResponse(
        analysis=ChartAnalysis(**result["analysis"]),
        validation=TradeValidationResult(**result["validation"]),
        coach=CoachExplanationResult(**result["coach"]),
        meta=result["meta"],
        multi_timeframe=MultiTimeframeConfirmation(**multi_timeframe) if multi_timeframe else None,
    )


@router.post(
    "/full-analysis/image",
    response_model=FullChartAnalysisResponse,
    summary="Levels 1 + 2 + 3 in one call, from a chart screenshot",
)
async def full_analysis_image(
    file: UploadFile = File(...),
    direction: str | None = Form(None),
    planned_rr: float | None = Form(None),
    has_m15_bos: bool = Form(False),
    has_m15_choch: bool = Form(False),
    has_m15_entry_confirmation: bool = Form(False),
    has_liquidity_sweep: bool = Form(False),
    min_rr: float = Form(2.0),
) -> FullChartAnalysisResponse:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError(f"Unsupported image type: {file.content_type}. Use PNG, JPEG, or WEBP.")
    image_bytes = await file.read()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValidationError("Image too large — please upload a screenshot under 8MB.")
    service = ChartService()
    result = await service.full_analysis_from_image(
        image_bytes,
        file.content_type,
        direction=direction,
        planned_rr=planned_rr,
        has_m15_bos=has_m15_bos,
        has_m15_choch=has_m15_choch,
        has_m15_entry_confirmation=has_m15_entry_confirmation,
        has_liquidity_sweep=has_liquidity_sweep,
        min_rr=min_rr,
    )
    return FullChartAnalysisResponse(
        analysis=ChartAnalysis(**result["analysis"]),
        validation=TradeValidationResult(**result["validation"]),
        coach=CoachExplanationResult(**result["coach"]),
        meta=result["meta"],
    )
