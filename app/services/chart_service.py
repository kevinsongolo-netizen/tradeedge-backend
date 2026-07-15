"""Chart Analysis Engine service (Sprint 10).

Orchestrates the two Level-1 reading paths (deterministic candle math,
best-effort vision AI), normalizes either into the canonical
``ChartAnalysis`` shape, and runs Level 2 (trade validation) / Level 3
(AI coach explanation) on top. No database access — chart analyses are
stateless by design in this first cut (see ``app/chart/__init__.py``
for the future-expansion note on trade journaling / AI review-after-
close, which would add persistence here without touching the engines).
"""
from __future__ import annotations

from typing import Any

from app.chart import normalize
from app.chart.candle_smc_engine import Candle, analyze_candles
from app.chart.coach_explainer import explain
from app.chart.personal_averaging_strategy import validate_personal_averaging
from app.chart.multi_timeframe import confirm_with_m15
from app.chart.trade_validator import _direction_from_bias, validate_trade
from app.chart.vision_provider import VisionProviderError, get_vision_provider
from app.errors import ValidationError
from app.schemas.chart import ChartAnalysis

_IMAGE_NOT_SUPPORTED_DETAIL = (
    "Screenshot analysis only sees one chart, so it can't check both the "
    "Daily bias and M15 Point of Interest your strategy requires -- paste "
    "Daily+M15 candle data instead (Chart Analysis Engine's \"candles\" mode, "
    "Live Feed, or the Scanner). Screenshot support for this strategy isn't built yet."
)


def _image_not_supported_validation() -> dict:
    """The screenshot-upload path can only read ONE chart, so it can
    never check the Daily bias AND M15 Point of Interest the user's one
    official strategy (Sprint 18 -- Personal Averaging Strategy)
    requires -- rather than silently falling back to a retired
    validator (a second, disagreeing strategy engine), this returns an
    honest WAIT with every rule marked NOT_CHECKED and a clear
    explanation of why."""
    not_checked = [
        {"rule": "Daily Bias", "status": "NOT_CHECKED", "detail": _IMAGE_NOT_SUPPORTED_DETAIL},
        {"rule": "M15 Order Block/FVG", "status": "NOT_CHECKED", "detail": _IMAGE_NOT_SUPPORTED_DETAIL},
        {"rule": "Entry Timing (near end of zone)", "status": "NOT_CHECKED", "detail": _IMAGE_NOT_SUPPORTED_DETAIL},
        {"rule": "Add-On Entry (2nd position)", "status": "NOT_CHECKED", "detail": _IMAGE_NOT_SUPPORTED_DETAIL},
    ]
    return {
        "tradeStatus": "INVALID",
        "direction": None,
        "confidence": 0,
        "reasonsPassed": [],
        "reasonsFailed": [f"✗ {_IMAGE_NOT_SUPPORTED_DETAIL}"],
        "ruleChecks": not_checked,
        "suggestedEntry": None,
        "stopLoss": None,
        "takeProfit": None,
        "riskReward": None,
        "recommendation": "WAIT",
        "strategy": "Personal Averaging Strategy (Daily Bias + M15 POI, no fixed SL/TP)",
        "dailyBias": None,
        "addOnSignal": False,
        "breakEvenPrice": None,
    }


class ChartService:
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

    def validate(self, analysis: ChartAnalysis, **kwargs) -> dict[str, Any]:
        return validate_trade(analysis, **kwargs)

    def coach(self, analysis: ChartAnalysis, validation: dict[str, Any], min_rr: float = 2.0) -> dict[str, Any]:
        return explain(analysis, validation, min_rr)

    async def full_analysis_from_candles(
        self, candles: list[dict], *, direction: str | None, planned_rr: float | None,
        has_m15_bos: bool, has_m15_choch: bool, has_m15_entry_confirmation: bool,
        has_liquidity_sweep: bool, min_rr: float, m15_candles: list[dict] | None = None,
        daily_candles: list[dict] | None = None, open_trade_in_loss: bool = False,
    ) -> dict[str, Any]:
        analysis_dict = await self.analyze_candles(candles)
        analysis = ChartAnalysis(**analysis_dict)

        multi_timeframe: dict[str, Any] | None = None
        if m15_candles:
            m15_analysis_dict = await self.analyze_candles(m15_candles)
            m15_analysis = ChartAnalysis(**m15_analysis_dict)
            # Still computed for informational display (BOS/CHOCH/trend
            # agreement on M15) -- purely descriptive now, no longer used
            # to gate anything (see the active strategy below).
            resolved_direction = direction or _direction_from_bias(analysis.bias) or "buy"
            multi_timeframe = confirm_with_m15(m15_analysis, resolved_direction)

        # --- ACTIVE STRATEGY (Sprint 18): Personal Averaging Strategy
        # (Daily Bias -> M15 POI -> Entry Timing -> Add-On Entry -- the
        # user's own rules, see app/chart/personal_averaging_strategy.py
        # for the exact logic and no-fixed-SL/TP rationale). Needs the
        # RAW SmcAnalysis for M15 (order block coordinates), not the
        # normalized ChartAnalysis shape used above, so the candle math
        # is run a second time here -- cheap, pure function, no I/O.
        #
        # The retired H4->M15 POI engine (app/chart/htf_ltf_ob_strategy.py)
        # and the even-older "Classic Bias" strategy
        # (app/chart/trade_validator.py) are both kept fully intact and
        # untouched for later reuse; only this block changed to swap
        # which validator is active:
        daily_smc_candles = [Candle(**c) for c in daily_candles] if daily_candles else []
        m15_smc = analyze_candles(m15_candles) if m15_candles else None
        validation = validate_personal_averaging(daily_smc_candles, m15_smc, open_trade_in_loss=open_trade_in_loss)

        coach_result = self.coach(analysis, validation, min_rr)
        return {
            "analysis": analysis_dict,
            "validation": validation,
            "coach": coach_result,
            "meta": None,
            "multi_timeframe": multi_timeframe,
        }

    async def full_analysis_from_image(
        self, image_bytes: bytes, mime_type: str, *, direction: str | None, planned_rr: float | None,
        has_m15_bos: bool, has_m15_choch: bool, has_m15_entry_confirmation: bool,
        has_liquidity_sweep: bool, min_rr: float,
    ) -> dict[str, Any]:
        """Screenshot-upload path. NOTE: this can only ever see ONE
        chart, so it can't run the ONE official H4->M15 POI strategy
        (which needs both timeframes) -- rather than quietly falling
        back to the retired Classic Bias validator (which would make
        this the one place in the app running a second, different
        strategy), it returns an explicit, clearly-explained WAIT. All
        of ``direction``/``planned_rr``/``has_m15_bos``/``has_m15_choch``/
        ``has_m15_entry_confirmation``/``has_liquidity_sweep`` are kept
        as accepted (unused) parameters only so this method's signature
        doesn't need to change for existing callers."""
        del direction, planned_rr, has_m15_bos, has_m15_choch, has_m15_entry_confirmation, has_liquidity_sweep
        analysis_dict, meta = await self.analyze_image(image_bytes, mime_type)
        analysis = ChartAnalysis(**analysis_dict)
        validation = _image_not_supported_validation()
        coach_result = self.coach(analysis, validation, min_rr)
        return {"analysis": analysis_dict, "validation": validation, "coach": coach_result, "meta": meta}
