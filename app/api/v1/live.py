"""Sprint 14 — Live MT5 Feed router.

``POST /api/v1/live/ingest`` — an MT5 Expert Advisor (or any other live
source) pushes fresh candles here on every new bar close. Runs the
same Level 1/2/3 pipeline as ``/chart/full-analysis/candles`` and
additionally persists the result so ``GET /api/v1/live/latest`` (used
by the website) can display it without the user re-pasting candles.

Pass ``?format=plain`` on the ingest call for a trivial-to-parse plain
text response (a few ``KEY=value`` lines) instead of JSON — MQL5 has no
built-in JSON parser, so the EA reads this directly and calls
``SendNotification()`` itself when ``STATUS=VALID``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.deps import get_current_user_id
from app.schemas.chart import (
    ChartAnalysis,
    CoachExplanationResult,
    FullChartAnalysisResponse,
    MultiTimeframeConfirmation,
    TradeValidationResult,
)
from app.schemas.live import LiveIngestRequest, LiveSnapshotOut
from app.services.live_service import LiveFeedService

router = APIRouter(prefix="/live", tags=["live"])


def _format_plain(result: dict) -> str:
    analysis = result["analysis"]
    validation = result["validation"]
    coach = result["coach"]
    lines = [
        f"STATUS={validation.get('tradeStatus', '')}",
        f"RECOMMENDATION={validation.get('recommendation', '')}",
        f"DIRECTION={validation.get('direction') or ''}",
        f"HEADLINE={coach.get('headline', '')}",
        f"CONFIDENCE={coach.get('confidence', {}).get('overall', '')}",
        f"TREND={analysis.get('trend', '')}",
    ]
    return "\n".join(lines) + "\n"


@router.post(
    "/ingest",
    summary="Sprint 14 — ingest fresh candles from a live source (e.g. an MT5 EA)",
)
async def ingest(
    body: LiveIngestRequest,
    format: str = Query(default="json", pattern="^(json|plain)$"),
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
):
    service = LiveFeedService(session)
    candles = [c.model_dump(by_alias=False) for c in body.candles]
    m15_candles = (
        [c.model_dump(by_alias=False) for c in body.m15_candles] if body.m15_candles else None
    )
    result = await service.ingest(
        user_id,
        body.symbol,
        body.timeframe,
        candles,
        direction=body.direction,
        planned_rr=body.planned_rr,
        has_m15_bos=body.has_m15_bos,
        has_m15_choch=body.has_m15_choch,
        has_m15_entry_confirmation=body.has_m15_entry_confirmation,
        has_liquidity_sweep=body.has_liquidity_sweep,
        min_rr=body.min_rr,
        m15_candles=m15_candles,
    )
    if format == "plain":
        return PlainTextResponse(_format_plain(result))
    multi_timeframe = result.get("multi_timeframe")
    return FullChartAnalysisResponse(
        analysis=ChartAnalysis(**result["analysis"]),
        validation=TradeValidationResult(**result["validation"]),
        coach=CoachExplanationResult(**result["coach"]),
        meta=result.get("meta"),
        multi_timeframe=MultiTimeframeConfirmation(**multi_timeframe) if multi_timeframe else None,
    )


@router.get(
    "/latest",
    response_model=LiveSnapshotOut,
    summary="Sprint 14 — fetch the most recently ingested live analysis for a symbol/timeframe",
)
async def latest(
    symbol: str,
    timeframe: str,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> LiveSnapshotOut:
    service = LiveFeedService(session)
    result = await service.latest(user_id, symbol, timeframe)
    return LiveSnapshotOut(**result)
