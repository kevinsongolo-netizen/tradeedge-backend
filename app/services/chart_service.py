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
from app.media.image_storage import ImageStorageProviderError, get_image_storage_provider

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
        self, image_bytes: bytes, mime_type: str, *, user_id: int, session_hint: str | None = None,
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

        # Sprint 20 Phase 3 -- the trader shouldn't have to upload the
        # same screenshot twice (once here for the read, again to
        # attach it to the trade): save it now and hand the URL back so
        # the frontend can carry it straight into the journal entry it
        # builds from this same extraction. Best-effort only -- a
        # storage failure must never block the vision read itself
        # (which already succeeded by this point) from reaching the
        # trader; they'd just save the trade with no screenshot
        # attached, same as before this feature existed.
        image_storage = get_image_storage_provider()
        screenshot_url: str | None = None
        try:
            screenshot_url = await image_storage.upload(image_bytes, mime_type, folder="tradeedge/entries")
        except ImageStorageProviderError:
            screenshot_url = None
        meta["screenshotUrl"] = screenshot_url

        candidate = candidate_from_vision_extraction(raw)
        # Sprint 20 Phase 5 -- the vision model can't read "session" off
        # a screenshot (nothing on the chart shows it); the frontend's
        # own session-detect call supplies it instead, so the live
        # pre-trade comparison uses it as a fingerprint dimension too,
        # not just already-saved trades. Best-effort/optional.
        if session_hint:
            candidate["session"] = session_hint
        trade_repo = TradeRepository(self.session)
        history = [t.to_engine_dict() for t in await trade_repo.list_all(user_id)]
        insight = build_setup_insight(candidate, history, raw_extraction=raw)

        # Sprint 20 Phase 4 -- the "complete trade fingerprint" ask.
        # ``extraction`` above is the narrow, UI-facing subset used for
        # display; ``fingerprint`` is the *entire* raw vision read
        # (trend, structure, order-block/FVG/BOS/CHOCH text, liquidity,
        # premium/discount, the trader's own entry/SL/TP/R:R, etc. --
        # everything in VISION_ANALYSIS_SCHEMA_HINT plus provider/
        # confidence metadata) verbatim, so the frontend can carry it
        # through unmodified into ``POST /trades``'s ``visionFingerprint``
        # field and the trade keeps a full record of exactly what the AI
        # saw on the screenshot, not just the handful of fields the UI
        # happens to render today.
        fingerprint = dict(raw)

        return {"extraction": extraction, "insight": insight, "meta": meta, "fingerprint": fingerprint}

    async def upload_screenshot(self, image_bytes: bytes, mime_type: str, *, folder: str = "tradeedge/exits") -> dict[str, Any]:
        """Sprint 20 Phase 3 -- plain screenshot upload with no vision
        analysis, for the optional "after exit" chart shot attached to
        an already-logged trade (or any other free-standing screenshot
        upload). Never raises on a storage failure -- returns
        ``url=None`` plus the reason, so the caller can tell the trader
        honestly that it didn't save without losing anything else they
        were doing."""
        image_storage = get_image_storage_provider()
        try:
            url = await image_storage.upload(image_bytes, mime_type, folder=folder)
        except ImageStorageProviderError as exc:
            return {"url": None, "isPlaceholder": image_storage.name == "placeholder", "error": str(exc)}
        return {"url": url, "isPlaceholder": image_storage.name == "placeholder", "error": None}
