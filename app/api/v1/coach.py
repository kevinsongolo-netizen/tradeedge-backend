"""AI Coach router — ``GET /api/v1/coach/insights`` (Section 4.6) and,
since Sprint 8, ``GET /api/v1/coach/deep-dive`` (Vision Phase 6)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.deps import get_current_user_id
from app.schemas.coach import (
    CoachDeepDive,
    CoachInsightsResponse,
    EdgePatternsResponse,
    PlaybookResponse,
    TradeReviewRequest,
    TradeReviewResult,
)
from app.services.coach_service import CoachService
from app.services.trade_review_service import TradeReviewService

router = APIRouter(prefix="/coach", tags=["coach"])


@router.get("/insights", response_model=CoachInsightsResponse, summary="Data-backed coaching insights")
async def coach_insights(
    limit: int = Query(default=6, ge=1, le=20),
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> CoachInsightsResponse:
    """Generated purely from calculated statistics/setup/mistake/health
    data — no hardcoded advice. Cached for 60s per user (Section 5.3)."""
    service = CoachService(session)
    insights = await service.insights(user_id, limit=limit)
    return CoachInsightsResponse(insights=insights)


@router.get("/deep-dive", response_model=CoachDeepDive, summary="Structured Q&A: why am I losing/winning, best/worst setup, etc.")
async def coach_deep_dive(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> CoachDeepDive:
    """Sprint 8 Phase 6 (Personal Trading Coach) — answers the vision
    doc's specific questions (why losing/winning, biggest mistake,
    best/worst setup, worst day to trade, best session, pair to stop
    trading) as structured fields rather than freeform text, built from
    the same statistics/mistake/setup/health data ``/coach/insights``
    uses."""
    service = CoachService(session)
    result = await service.deep_dive(user_id)
    return CoachDeepDive(**result)


@router.get(
    "/playbook",
    response_model=PlaybookResponse,
    summary="Sprint 20 Phase 3 — My Best Setups (per-POI-type win rate, R:R, best session/day, example screenshots)",
)
async def coach_playbook(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> PlaybookResponse:
    """Ranked purely from this trader's own logged history -- never a
    fixed "good setup" list. A POI type only appears once it's been
    logged enough times to mean something (see
    app/engines/playbook_engine.py's PLAYBOOK_MIN_SAMPLE)."""
    service = CoachService(session)
    result = await service.playbook(user_id)
    return PlaybookResponse(**result)


@router.get(
    "/edge-patterns",
    response_model=EdgePatternsResponse,
    summary="Sprint 20 Phase 5 — Best Pattern (multi-dimensional edge: pair+direction+timeframe+POI+zone+session)",
)
async def coach_edge_patterns(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> EdgePatternsResponse:
    """"Once enough trades exist, I want the AI to automatically
    discover my edge" -- ranked purely from this trader's own logged
    history, never a hardcoded "good" combination. A pattern only
    appears once that exact six-dimension combination has been logged
    enough times to mean something (see
    app/engines/edge_pattern_engine.py's EDGE_MIN_SAMPLE)."""
    service = CoachService(session)
    result = await service.edge_patterns(user_id)
    return EdgePatternsResponse(**result)


@router.post(
    "/review-trade",
    response_model=TradeReviewResult,
    summary="Sprint 11 — AI review-after-close for a single closed trade",
)
async def review_trade(
    body: TradeReviewRequest,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> TradeReviewResult:
    """Takes the whole trade in the request body (same fields the
    journal already collects), so it works whether or not the trade
    has been synced to the backend yet. Never just labels a trade win/
    loss: explains what worked, what went wrong, and the one lesson
    worth remembering, from the rules-followed/tags/exit-reason/R:R
    fields already captured when the trade was logged -- and, since
    Sprint 20 Phase 2 #4, also compares this trade's stop/target sizing
    and outcome against the trader's own similar past trades (loaded
    from the DB for this user), never a fixed rule."""
    service = TradeReviewService(session)
    result = await service.review(user_id, body.to_candidate_dict())
    return TradeReviewResult(**result)
