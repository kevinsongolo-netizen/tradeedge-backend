"""Pre-Trade Check service.

v3 — adds a "use Live Feed" path alongside the v2 candle-paste path,
for traders whose MT5 EA is already pushing live candles and have no
easy way to hand-copy raw OHLC rows. Both paths converge on the same
ONE official H4->M15 POI strategy
(``app.chart.htf_ltf_ob_strategy.validate_h4_m15_ob``) -- the live path
just reuses whatever the Live MT5 Feed (Sprint 14) already computed for
that symbol/timeframe instead of re-running the candle math. ML
win-probability and similar-trade history are computed ONLY when the
strategy itself already says VALID, and are always supplementary --
they can add color, never change VALID to WAIT or vice versa (per the
user's explicit rule that ML must never override the trading rules).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.chart.candle_smc_engine import Candle, analyze_candles
from app.chart.personal_averaging_strategy import validate_personal_averaging
from app.db.repositories.live_snapshot_repo import LiveSnapshotRepository
from app.engines.assistant_engine import analyze_pretrade_from_strategy
from app.errors import NotFoundError, ValidationError
from app.services.ml_prediction_service import MLPredictionService, NoActiveModelError
from app.services.similar_service import SimilarService


def _candidate_to_similar_shape(candidate: dict[str, Any]) -> dict[str, Any]:
    """Adapts the strategy-derived candidate (snake_case) into the
    camelCase, tag-list shape ``search_similar()`` expects (same shape
    ``Trade.to_engine_dict()`` produces). BOS/CHOCH/liquidity-sweep tags
    are intentionally left empty -- the active strategy doesn't track
    them, so there's nothing honest to tag here anymore."""
    return {
        "pair": candidate.get("pair"),
        "direction": candidate.get("direction"),
        "asset": candidate.get("asset"),
        "session": candidate.get("session"),
        "h4Trend": candidate.get("h4_trend"),
        "h4PoiType": candidate.get("h4_poi_type"),
        "m15Confirmations": [],
        "rr": candidate.get("planned_rr"),
        "confidence": candidate.get("confidence"),
    }


def _validation_base(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_status": validation["tradeStatus"],
        "direction": validation["direction"],
        "rule_checks": validation["ruleChecks"],
        "reasons_passed": validation["reasonsPassed"],
        "reasons_failed": validation["reasonsFailed"],
        "suggested_entry": validation["suggestedEntry"],
        "stop_loss": validation["stopLoss"],
        "take_profit": validation["takeProfit"],
        "risk_reward": validation["riskReward"],
        "recommendation": validation["recommendation"],
        "strategy": validation.get("strategy"),
        "daily_bias": validation.get("dailyBias"),
        "add_on_signal": validation.get("addOnSignal", False),
        "break_even_price": validation.get("breakEvenPrice"),
    }


class AssistantService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.prediction_service = MLPredictionService(session)
        self.similar_service = SimilarService(session)
        self.live_snapshot_repo = LiveSnapshotRepository(session)

    async def _finish(
        self, user_id: int, *, pair: str, asset: str | None, session_name: str | None, validation: dict[str, Any]
    ) -> dict[str, Any]:
        """Shared tail for both entry paths: given a validation dict
        (however it was produced), decide whether to run the
        supplementary ML/similar-trade layer -- never for a WAIT (rule
        #5), always without touching ``validation``'s own decision."""
        base = _validation_base(validation)

        if validation["tradeStatus"] != "VALID":
            return {
                **base,
                "ml_available": False,
                "historical_reasons": [
                    "Your official strategy says WAIT -- no ML or history lookup is run until it says VALID."
                ],
            }

        candidate = {
            "pair": pair,
            "asset": asset,
            "direction": validation["direction"],
            "session": session_name,
            "h4_trend": "Bullish" if validation["direction"] == "buy" else "Bearish",
            "h4_poi_type": None,
            "has_bos": False,
            "has_choch": False,
            "has_liquidity_sweep": False,
            "planned_rr": validation["riskReward"],
            "rule_score": None,
            "execution_score": None,
            "confidence": validation["confidence"],
            "emotion": None,
        }

        try:
            ml_result = await self.prediction_service.predict(user_id, candidate)
        except NoActiveModelError:
            # Still useful before the user has ever trained a model --
            # degrades to a rule/history-only estimate.
            ml_result = None

        similar_result = await self.similar_service.find_similar(
            user_id,
            _candidate_to_similar_shape(candidate),
            min_similarity=50.0,
            limit=20,
        )

        extra = analyze_pretrade_from_strategy(validation, ml_result=ml_result, similar_result=similar_result)
        return {**base, **extra}

    async def analyze_pretrade_candles(
        self,
        user_id: int,
        *,
        pair: str,
        asset: str | None,
        session_name: str | None,
        daily_candles: list[dict],
        m15_candles: list[dict],
        open_trade_in_loss: bool = False,
    ) -> dict[str, Any]:
        try:
            daily = [Candle(**c) for c in daily_candles]
            m15_smc = analyze_candles(m15_candles)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        validation = validate_personal_averaging(daily, m15_smc, open_trade_in_loss=open_trade_in_loss)
        return await self._finish(user_id, pair=pair, asset=asset, session_name=session_name, validation=validation)

    async def analyze_pretrade_live(
        self,
        user_id: int,
        *,
        pair: str,
        asset: str | None,
        session_name: str | None,
        symbol: str,
        timeframe: str,
    ) -> dict[str, Any]:
        """Reuses whatever the Live MT5 Feed already computed for this
        symbol/timeframe (same data the Chart Analysis Engine's "Live
        feed" mode and the Scanner read) instead of requiring the user
        to hand-copy H4+M15 candle rows."""
        row = await self.live_snapshot_repo.get(user_id, symbol, timeframe)
        if row is None:
            raise NotFoundError(
                f"No live data yet for {symbol} {timeframe}. Make sure your MT5 EA is "
                "attached and running, and that it's pushed at least one update."
            )
        return await self._finish(
            user_id, pair=pair, asset=asset, session_name=session_name, validation=row.validation
        )
