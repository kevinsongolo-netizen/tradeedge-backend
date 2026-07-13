"""Sprint 12 — news/economic calendar filter router.

``POST /api/v1/news/check-calendar`` — checks whether high-impact
economic news falls near a planned trade time. Stateless, no auth/DB
dependency, same pattern as the Chart Analysis Engine and tools
routers. Uses ``PlaceholderCalendarProvider`` (clearly-labeled example
data) until ``FINNHUB_API_KEY`` is configured — see
``app/news/calendar_provider.py``.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.schemas.news import NewsCheckRequest, NewsCheckResult
from app.services.news_service import NewsService

router = APIRouter(prefix="/news", tags=["news"])


@router.post(
    "/check-calendar",
    response_model=NewsCheckResult,
    summary="Sprint 12 — check for high-impact economic news near a planned trade time",
)
async def check_calendar(body: NewsCheckRequest) -> NewsCheckResult:
    service = NewsService()
    result = await service.check(
        body.planned_time,
        buffer_minutes=body.buffer_minutes,
        currencies=body.currencies,
        min_impact=body.min_impact,
    )
    return NewsCheckResult(**result)
