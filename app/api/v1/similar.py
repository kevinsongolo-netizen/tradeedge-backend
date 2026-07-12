"""Similar-trade router — ``POST /api/v1/ai/similar`` (Section 4.4)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.deps import get_current_user_id
from app.schemas.similar import SimilarSearchRequest, SimilarSearchResult
from app.services.similar_service import SimilarService

router = APIRouter(prefix="/ai", tags=["similar"])


@router.post("/similar", response_model=SimilarSearchResult, summary="Weighted similar-trade search")
async def find_similar_trades(
    body: SimilarSearchRequest,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> SimilarSearchResult:
    """Ranks a user's journal history against ``candidate`` using the
    weighted-v1 similarity algorithm (Section 7), or the legacy binary
    algorithm if ``algorithm="legacy"`` is requested."""
    service = SimilarService(session)
    result = await service.find_similar(
        user_id,
        # Bug found during Sprint 8 review: this used to_model_kwargs()
        # (snake_case: h4_trend, h4_poi_type, m15_confirmations, ...),
        # but search_similar()/search_similar_legacy() read camelCase
        # keys (h4Trend, h4PoiType, m15Confirmations, ...) — the same
        # shape Trade.to_engine_dict() produces for history entries.
        # Net effect: every SMC-structure feature (H4 trend, POI,
        # premium/discount, BOS/CHOCH/liquidity sweep tags) was silently
        # excluded from every similarity score, even though those
        # features carry ~44 of the algorithm's 100 weight points by
        # design. See TradeBase.to_candidate_dict() for the fix and a
        # reproduction of the bug's impact.
        body.candidate.to_candidate_dict(),
        min_similarity=body.min_similarity,
        limit=body.limit,
        algorithm=body.algorithm,
    )
    return SimilarSearchResult(**result)
