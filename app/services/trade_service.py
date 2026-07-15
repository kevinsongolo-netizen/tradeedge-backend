"""Trade Service — CRUD orchestration + re-analysis on save (Section
5.2, Section 9.1's save-a-trade flow).

Owns the transaction: persist the trade, run the AI engines against
the user's history, persist the resulting ``ai_analyses`` row, cache
the scores back onto ``trades``, and invalidate the stats/coach caches
— all inside one unit of work per call.
"""
from __future__ import annotations

from datetime import date as date_, datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trade import Trade
from app.db.repositories.analysis_repo import AnalysisRepository
from app.db.repositories.trade_repo import TradeRepository
from app.errors import NotFoundError
from app.services.ai_service import AIService
from app.services.cache import coach_cache, stats_cache


def _trade_to_out_dict(trade: Trade) -> dict[str, Any]:
    data = trade.to_engine_dict()
    data["createdAt"] = trade.created_at
    data["updatedAt"] = trade.updated_at
    return data


class TradeService:
    """Trade CRUD + the synchronous re-analysis pipeline."""

    def __init__(self, session: AsyncSession, trade_repo: TradeRepository | None = None) -> None:
        self.session = session
        self.trade_repo = trade_repo or TradeRepository(session)
        self.analysis_repo = AnalysisRepository(session)
        self.ai_service = AIService(session)

    async def _invalidate_caches(self, user_id: int) -> None:
        stats_cache.invalidate(user_id)
        coach_cache.invalidate(user_id)

    async def _analyze_and_persist(self, user_id: int, trade: Trade) -> None:
        """Runs the AI pipeline against the trade's prior history and
        writes both the versioned ``ai_analyses`` row and the cached
        score columns on ``trades`` (Section 9.1, steps 3-5)."""
        history = [
            t.to_engine_dict() for t in await self.trade_repo.list_all(user_id) if t.id != trade.id
        ]
        weights = await self.ai_service.get_weights(user_id)
        result = AIService.analyze_trade(
            trade.to_engine_dict(),
            history,
            rule_weights=weights["rule"],
            similarity_weights=weights["similarity"],
        )

        await self.analysis_repo.insert(
            user_id,
            trade.id,
            {
                "rule_score": result["ruleScore"],
                "execution_score": result["executionScore"],
                "overall_score": result["overallScore"],
                "recommendation": result["recommendation"],
                "grade": result["grade"],
                "rule_breakdown": result["ruleBreakdown"],
                "execution_breakdown": result["executionBreakdown"],
                "passed_reasons": result["passedReasons"],
                "missing_confirmations": result["missingConfirmations"],
                "strengths": result["strengths"],
                "mistakes": result["mistakes"],
                "suggestions": result["suggestions"],
                "rule_engine_version": result["ruleEngineVersion"],
                "execution_engine_version": result["executionEngineVersion"],
                "weights_snapshot": result["weightsSnapshot"],
            },
        )
        await self.trade_repo.update_cached_scores(
            trade,
            rule_score=result["ruleScore"],
            execution_score=result["executionScore"],
            overall_score=result["overallScore"],
            rule_recommendation=result["recommendation"],
        )

    async def create_trade(self, user_id: int, trade_in: dict[str, Any]) -> dict[str, Any]:
        """create_trade(user_id, trade_in) — upsert + synchronous
        re-analysis, all in one transaction (Section 9.1)."""
        trade_id = trade_in["id"]
        model_kwargs = {k: v for k, v in trade_in.items() if k != "id"}
        trade = await self.trade_repo.upsert(user_id, trade_id, model_kwargs)
        await self._analyze_and_persist(user_id, trade)
        await self._invalidate_caches(user_id)
        await self.session.commit()
        await self.session.refresh(trade)
        return _trade_to_out_dict(trade)

    async def get_trade(self, user_id: int, trade_id: str) -> dict[str, Any]:
        trade = await self.trade_repo.get(user_id, trade_id)
        if trade is None:
            raise NotFoundError(f"Trade {trade_id} not found")
        return _trade_to_out_dict(trade)

    async def list_trades(
        self,
        user_id: int,
        *,
        pair: str | None = None,
        session_name: str | None = None,
        date_from: date_ | None = None,
        date_to: date_ | None = None,
        outcome: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        rows, next_cursor = await self.trade_repo.list_page(
            user_id,
            pair=pair,
            session_name=session_name,
            date_from=date_from,
            date_to=date_to,
            outcome=outcome,
            limit=limit,
            cursor=cursor,
        )
        return {"items": [_trade_to_out_dict(t) for t in rows], "nextCursor": next_cursor}

    async def update_trade(self, user_id: int, trade_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """update_trade(user_id, trade_id, patch) — partial update.
        Re-analysis always runs since almost every field is
        scoring-relevant; this keeps behavior simple and correct rather
        than trying to enumerate "safe" fields."""
        existing = await self.trade_repo.get(user_id, trade_id)
        if existing is None:
            raise NotFoundError(f"Trade {trade_id} not found")
        trade = await self.trade_repo.upsert(user_id, trade_id, patch)
        await self._analyze_and_persist(user_id, trade)
        await self._invalidate_caches(user_id)
        await self.session.commit()
        await self.session.refresh(trade)
        return _trade_to_out_dict(trade)

    async def delete_trade(self, user_id: int, trade_id: str) -> None:
        deleted = await self.trade_repo.delete(user_id, trade_id)
        if not deleted:
            raise NotFoundError(f"Trade {trade_id} not found")
        await self._invalidate_caches(user_id)
        await self.session.commit()

    async def delete_all_trades(self, user_id: int) -> int:
        """Sprint 18 -- bulk-clears the whole journal (e.g. starting
        fresh on a new MT5 account, per the user's own explicit
        request). Returns how many trades were removed."""
        count = await self.trade_repo.delete_all(user_id)
        await self._invalidate_caches(user_id)
        await self.session.commit()
        return count

    async def bulk_upsert(self, user_id: int, items: list[dict[str, Any]]) -> dict[str, Any]:
        """bulk_upsert(user_id, items) — used by ``POST /trades/bulk``
        and the localStorage migration script. Each trade is analyzed
        individually; a failure on one row doesn't abort the batch."""
        inserted = 0
        updated = 0
        failed: list[dict[str, str]] = []
        for item in items:
            trade_id = item.get("id")
            if not trade_id:
                failed.append({"id": "", "error": "Missing id"})
                continue
            try:
                existed = await self.trade_repo.get(user_id, trade_id) is not None
                model_kwargs = {k: v for k, v in item.items() if k != "id"}
                trade = await self.trade_repo.upsert(user_id, trade_id, model_kwargs)
                await self._analyze_and_persist(user_id, trade)
                if existed:
                    updated += 1
                else:
                    inserted += 1
            except Exception as exc:  # noqa: BLE001 - one bad row shouldn't abort the batch
                failed.append({"id": trade_id, "error": str(exc)})
        await self._invalidate_caches(user_id)
        await self.session.commit()
        return {"inserted": inserted, "updated": updated, "failed": failed}
