"""AI Service — orchestrates the rule + execution + reason engines for
one trade (Section 5.2: ``analyze_trade``, ``rule_only``,
``execution_only``, ``get_weights``, ``set_weights``).

Pure computation only — this service never writes to ``trades`` or
``ai_analyses``; ``TradeService`` calls it and persists the result
itself (Section 9.1's save-a-trade flow). This keeps "compute a score"
and "what do we do with that score" cleanly separated.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.weights_repo import WeightsRepository
from app.engines.execution_engine import (
    EXECUTION_SCORE_WEIGHTS,
    combine_scores,
    compute_execution_score,
    execution_outcome_grade,
)
from app.engines.rule_engine import DEFAULT_RULE_SCORE_WEIGHTS, compute_rule_score, normalize_rule_weights
from app.engines.execution_engine import EXECUTION_ENGINE_VERSION
from app.engines.rule_engine import RULE_ENGINE_VERSION
from app.engines.similar_engine import DEFAULT_SIMILARITY_WEIGHTS, normalize_similarity_weights


class AIService:
    """Runs the rule/execution/reason engines for a single trade and
    manages per-user weight overrides."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.weights_repo = WeightsRepository(session)

    async def get_weights(self, user_id: int) -> dict[str, dict[str, float]]:
        """Returns the normalized weight set for a user: their override
        (if any) merged over each engine's defaults, per Section 4.3's
        ``GET /ai/weights``."""
        row = await self.weights_repo.get(user_id)
        rule_weights = normalize_rule_weights((row.rule_weights if row else None))
        execution_weights = {**{}, **(row.execution_weights if row and row.execution_weights else {})}
        # Execution weights aren't renormalized in the JS engine (they're
        # fixed point values summing to 100 already) — only overridden.
        from app.engines.execution_engine import EXECUTION_SCORE_WEIGHTS

        merged_execution = {**EXECUTION_SCORE_WEIGHTS, **execution_weights}
        similarity_weights = normalize_similarity_weights(row.similarity_weights if row else None)
        return {"rule": rule_weights, "execution": merged_execution, "similarity": similarity_weights}

    async def set_weights(self, user_id: int, payload: dict[str, dict[str, float] | None]) -> dict[str, dict[str, float]]:
        """Persists a per-user weight override and returns the
        normalized result (Section 4.3's ``PUT /ai/weights``)."""
        await self.weights_repo.upsert(
            user_id,
            {
                "rule_weights": payload.get("rule"),
                "execution_weights": payload.get("execution"),
                "similarity_weights": payload.get("similarity"),
            },
        )
        await self.session.commit()
        return await self.get_weights(user_id)

    @staticmethod
    def rule_only(trade: dict[str, Any], weights: dict[str, float] | None = None) -> dict:
        """rule_only(trade, weights) — ``POST /ai/rule``."""
        return compute_rule_score(trade, weights)

    @staticmethod
    def execution_only(trade: dict[str, Any], history: list[dict[str, Any]], weights: dict[str, float] | None = None) -> dict:
        """execution_only(trade, history) — ``POST /ai/execution``.
        (Execution weights are fixed-point today; ``weights`` is accepted
        for forward compatibility with a future override.)"""
        return compute_execution_score(trade, history)

    @staticmethod
    def analyze_trade(
        trade: dict[str, Any],
        history: list[dict[str, Any]],
        *,
        rule_weights: dict[str, float] | None = None,
        similarity_weights: dict[str, float] | None = None,
    ) -> dict:
        """analyze_trade(trade, history) — runs rule + execution engines
        and combines them into the ``AnalyzeResult`` shape (Section 4.3).
        Execution fields are ``None`` for an open trade (no exit/pnl yet).

        This is a pure computation: no persistence happens here. Callers
        that need to persist (``TradeService``) take the returned dict
        and write ``ai_analyses`` + the cached ``trades`` columns
        themselves.
        """
        rule_result = compute_rule_score(trade, rule_weights)

        is_closed = trade.get("exit") not in (None, "") or trade.get("pnl") not in (None, "")
        if is_closed:
            execution_result = compute_execution_score(trade, history)
            overall = combine_scores(rule_result["score"], execution_result["score"])
        else:
            execution_result = None
            overall = combine_scores(rule_result["score"], None)

        weights_snapshot = {
            "rule": rule_result["weights"],
            "execution": EXECUTION_SCORE_WEIGHTS,
        }

        return {
            "ruleScore": rule_result["score"],
            "executionScore": execution_result["score"] if execution_result else None,
            "overallScore": overall,
            "recommendation": rule_result["recommendation"],
            "grade": execution_result["grade"] if execution_result else None,
            "ruleBreakdown": rule_result["reasons"],
            "executionBreakdown": execution_result["reasons"] if execution_result else [],
            "passedReasons": rule_result["passedReasons"],
            "missingConfirmations": rule_result["missingConfirmations"],
            "strengths": execution_result["strengths"] if execution_result else [],
            "mistakes": execution_result["mistakes"] if execution_result else [],
            "suggestions": execution_result["suggestions"] if execution_result else [],
            "ruleEngineVersion": RULE_ENGINE_VERSION,
            "executionEngineVersion": EXECUTION_ENGINE_VERSION,
            "weightsSnapshot": weights_snapshot,
        }
