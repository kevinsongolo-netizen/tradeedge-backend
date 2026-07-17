"""Chart Analysis Engine service (Sprint 10; rewritten Sprint 20).

Sprint 20 -- screenshot-first workflow. The old Level 2 (rule
validation) / Level 3 (rule narration) steps are gone from this
service: they lived in ``app/_legacy/`` now (Classic Bias, the H4->M15
POI engine, and the Personal Averaging Strategy, none of which are
called from here anymore). In their place, ``full_analysis_from_image``
does: read the screenshot (Level 1, vision AI) -> compare the read
setup against the trader's own trade history (weighted similarity,
``app/engines/setup_insight_engine.py``) -> return the setup +
insight. No PASS/FAIL, no VALID/INVALID, no recommendation -- the
trader decides, the app just says "have I seen something like this
before, and how did it go?"

``analyze_candles``/``analyze_image`` (Level 1 only, no verdict of any
kind) are kept as-is -- they're generic chart-reading utilities, not
part of the retired strategy, and stay useful on their own.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.chart import normalize
from app.chart.candle_smc_engine import analyze_candles
from app.chart.vision_provider import VisionProviderError, get_vision_provider
from app.db.repositories.trade_repo import TradeRepository
from app.engines.setup_insight_engine import build_setup_insight, candidate_from_vision_extraction
from app.errors import ValidationError

# Raw vision-provider fields surfaced directly to the UI as the
# "extraction" -- what the AI read off the screenshot, before any
# comparison against trade history happens.
_EXTRACTION_FIELDS = (
    "pair", "timeframe", "orderDirection", "orderType", "entry", "stopLoss",
    "takeProfit", "riskReward", "lots", "poiType", "trend", "structure",
    "currentPriceContext", "liquidity", "latestEvent", "fvgStatus",
    "premiumDiscount", "readConfidence", "numberConsistencyWarning",
)


class ChartService:
    def __init__(self, session: AsyncSession | None = None) -> None:
        # Only needed by full_analysis_from_image (fetches trade history
        # for the similarity comparison) -- analyze_candles/analyze_image
        # are pure Level-1 reads and never touch the database.
        self.session = session

    async def analyze_candles(self, candles: list[dict]) -> dict[str, Any]:
        try:
            smc = analyze_candles(candles)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return normalize.from_candle_analysis(smc)

    async def analyze_image(self, image_bytes: bytes, mime_type: str) -> tuple[dict[str, Any], dict[str, Any]]:
        provider = get_vision_provider()
        try:
            raw = await provider.analyze_screenshot(image_bytes, mime_type)
        except VisionProviderError as exc:
            raise ValidationError(f"Could not analyze image: {exc}") from exc
        analysis_dict = normalize.from_vision_analysis(raw)
        meta = {"provider": raw.get("provider", provider.name), "isPlaceholder": raw.get("isPlaceholder", False)}
        return analysis_dict, meta

    async def full_analysis_from_image(
        self, image_bytes: bytes, mime_type: str, *, user_id: int,
    ) -> dict[str, Any]:
        """The screenshot-first workflow's one call: read the
        screenshot, compare it against the trader's own trade history,
        return both -- no verdict. Requires a DB session (passed to the
        constructor) to load that history."""
        if self.session is None:
            raise RuntimeError("ChartService.full_analysis_from_image requires a DB session.")

        provider = get_vision_provider()
        try:
            raw = await provider.analyze_screenshot(image_bytes, mime_type)
        except VisionProviderError as exc:
            raise ValidationError(f"Could not analyze image: {exc}") from exc

        meta = {"provider": raw.get("provider", provider.name), "isPlaceholder": raw.get("isPlaceholder", False)}
        extraction = {field: raw.get(field) for field in _EXTRACTION_FIELDS}

        candidate = candidate_from_vision_extraction(raw)
        trade_repo = TradeRepository(self.session)
        history = [t.to_engine_dict() for t in await trade_repo.list_all(user_id)]
        insight = build_setup_insight(candidate, history)

        return {"extraction": extraction, "insight": insight, "meta": meta}
