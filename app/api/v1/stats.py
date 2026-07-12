"""Statistics / strategy-health / setup / mistake router —
``/api/v1/stats/*`` (Section 4.5)."""
from __future__ import annotations

from datetime import date as date_

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.deps import get_current_user_id
from app.schemas.stats import (
    ChartData,
    MistakeAnalysisResult,
    SetupAnalysisResult,
    StatisticsResult,
    StrategyHealthResult,
)
from app.services.stats_service import StatsFilters, StatsService

router = APIRouter(prefix="/stats", tags=["stats"])


def _filters(
    pair: str | None = None,
    session_name: str | None = Query(default=None, alias="session"),
    date_from: date_ | None = None,
    date_to: date_ | None = None,
) -> StatsFilters:
    return StatsFilters(pair=pair, session_name=session_name, date_from=date_from, date_to=date_to)


@router.get("/summary", response_model=StatisticsResult, summary="Full performance statistics")
async def stats_summary(
    filters: StatsFilters = Depends(_filters),
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> StatisticsResult:
    service = StatsService(session)
    result = await service.summary(user_id, filters)
    return StatisticsResult(**result)


@router.get("/charts", response_model=ChartData, summary="Chart series data")
async def stats_charts(
    filters: StatsFilters = Depends(_filters),
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> ChartData:
    service = StatsService(session)
    result = await service.charts(user_id, filters)
    return ChartData(**result)


@router.get("/strategy-health", response_model=StrategyHealthResult, summary="Strategy health scorecard")
async def stats_strategy_health(
    filters: StatsFilters = Depends(_filters),
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> StrategyHealthResult:
    service = StatsService(session)
    result = await service.strategy_health(user_id, filters)
    return StrategyHealthResult(**result)


@router.get("/setups", response_model=SetupAnalysisResult, summary="Best-performing setup dimensions")
async def stats_setups(
    filters: StatsFilters = Depends(_filters),
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> SetupAnalysisResult:
    service = StatsService(session)
    result = await service.setups(user_id, filters)
    return SetupAnalysisResult(**result)


@router.get("/mistakes", response_model=MistakeAnalysisResult, summary="Mistake/habit analysis")
async def stats_mistakes(
    filters: StatsFilters = Depends(_filters),
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> MistakeAnalysisResult:
    service = StatsService(session)
    result = await service.mistakes(user_id, filters)
    return MistakeAnalysisResult(**result)
