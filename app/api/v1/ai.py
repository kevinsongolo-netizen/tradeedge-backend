"""AI analysis router — ``/api/v1/ai/*`` (Section 4.3).

``/ai/analyze``, ``/ai/rule``, and ``/ai/execution`` are all
"check this trade" endpoints: they run the engines against an ad-hoc
payload (which may not exist as a persisted trade yet) and never write
to the database. Persisted scoring lives on the trades router
(``create_trade``/``update_trade`` call ``AIService`` themselves).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.trade_repo import TradeRepository
from app.db.session import get_db_session
from app.deps import get_current_user_id
from app.engines.execution_engine import EXECUTION_ENGINE_VERSION
from app.engines.rule_engine import RULE_ENGINE_VERSION
from app.errors import NotFoundError
from app.schemas.ai import (
    AnalysisHistoryItem,
    AnalysisHistoryResponse,
    AnalyzeResult,
    ExecutionOnlyResult,
    RuleOnlyResult,
    WeightsPayload,
)
from app.schemas.trade import TradeAnalyzeIn
from app.services.ai_service import AIService

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/analyze", response_model=AnalyzeResult, summary="Analyze a trade without saving")
async def analyze_trade(
    body: TradeAnalyzeIn,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> AnalyzeResult:
    """Runs rule + execution engines on an ad-hoc payload (Section 9.2's
    "analyze without saving" flow). Execution fields are ``None`` if the
    trade has no ``exit``/``pnl`` yet (still open)."""
    trade_repo = TradeRepository(session)
    ai_service = AIService(session)
    history = [t.to_engine_dict() for t in await trade_repo.list_all(user_id)]
    weights = await ai_service.get_weights(user_id)
    result = AIService.analyze_trade(
        body.to_candidate_dict(), history, rule_weights=weights["rule"], similarity_weights=weights["similarity"]
    )
    return AnalyzeResult(**result)


@router.post("/rule", response_model=RuleOnlyResult, summary="Rule engine only")
async def rule_only(
    body: TradeAnalyzeIn,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> RuleOnlyResult:
    ai_service = AIService(session)
    weights = await ai_service.get_weights(user_id)
    result = AIService.rule_only(body.to_candidate_dict(), weights["rule"])
    return RuleOnlyResult(
        ruleScore=result["score"],
        recommendation=result["recommendation"],
        ruleBreakdown=result["reasons"],
        passedReasons=result["passedReasons"],
        missingConfirmations=result["missingConfirmations"],
        ruleEngineVersion=result["ruleVersion"],
        weights=result["weights"],
    )


@router.post("/execution", response_model=ExecutionOnlyResult, summary="Execution engine only")
async def execution_only(
    body: TradeAnalyzeIn,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> ExecutionOnlyResult:
    trade_repo = TradeRepository(session)
    history = [t.to_engine_dict() for t in await trade_repo.list_all(user_id)]
    result = AIService.execution_only(body.to_candidate_dict(), history)
    return ExecutionOnlyResult(
        executionScore=result["score"],
        grade=result["grade"],
        executionBreakdown=result["reasons"],
        strengths=result["strengths"],
        mistakes=result["mistakes"],
        suggestions=result["suggestions"],
        executionEngineVersion=result["executionVersion"],
    )


@router.get("/weights", summary="Get current engine weights")
async def get_weights(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    ai_service = AIService(session)
    return await ai_service.get_weights(user_id)


@router.put("/weights", summary="Override engine weights")
async def set_weights(
    body: WeightsPayload,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Any missing key falls back to the engine's own default; the
    normalized (sum-to-100) result is returned."""
    ai_service = AIService(session)
    return await ai_service.set_weights(user_id, body.model_dump(by_alias=False))


@router.get(
    "/trades/{trade_id}/analyses",
    response_model=AnalysisHistoryResponse,
    summary="Scoring history for one trade",
)
async def trade_analysis_history(
    trade_id: str,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> AnalysisHistoryResponse:
    from app.db.repositories.analysis_repo import AnalysisRepository

    trade_repo = TradeRepository(session)
    trade = await trade_repo.get(user_id, trade_id)
    if trade is None:
        raise NotFoundError(f"Trade {trade_id} not found")

    analysis_repo = AnalysisRepository(session)
    rows = await analysis_repo.list_for_trade(user_id, trade_id)
    items = [
        AnalysisHistoryItem(
            id=row.id,
            tradeId=row.trade_id,
            ruleScore=row.rule_score,
            executionScore=row.execution_score,
            overallScore=row.overall_score,
            recommendation=row.recommendation,
            grade=row.grade,
            ruleEngineVersion=row.rule_engine_version,
            executionEngineVersion=row.execution_engine_version,
            createdAt=row.created_at.isoformat(),
        )
        for row in rows
    ]
    return AnalysisHistoryResponse(items=items)
