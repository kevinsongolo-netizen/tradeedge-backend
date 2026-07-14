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
from app.chart.candle_smc_engine import analyze_candles
from app.chart.coach_explainer import explain
from app.chart.htf_ltf_ob_strategy import validate_h4_m15_ob
from app.chart.multi_timeframe import confirm_with_m15
from app.chart.trade_validator import _direction_from_bias, validate_trade
from app.chart.vision_provider import VisionProviderError, get_vision_provider
from app.errors import ValidationError
from app.schemas.chart import ChartAnalysis


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

        # --- ACTIVE STRATEGY: H4 -> M15 Order Block (the user's own
        # rules -- see app/chart/htf_ltf_ob_strategy.py for the exact
        # touch/entry/SL/TP logic). Needs the RAW SmcAnalysis objects
        # (order block coordinates, price_in_order_block), not the
        # normalized ChartAnalysis shape used above, so the candle math
        # is run a second time here -- cheap, pure function, no I/O.
        #
        # The previous "Classic Bias" strategy (trend + premium/discount
        # + BOS/CHOCH, min-R:R gate -- app/chart/trade_validator.py) is
        # kept fully intact and untouched for later reuse; only this one
        # line changed to swap which validator is active:
        h4_smc = analyze_candles(candles)
        m15_smc = analyze_candles(m15_candles) if m15_candles else None
        validation = validate_h4_m15_ob(h4_smc, m15_smc)

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
        analysis_dict, meta = await self.analyze_image(image_bytes, mime_type)
        analysis = ChartAnalysis(**analysis_dict)
        validation = self.validate(
            analysis,
            direction=direction,
            planned_rr=planned_rr,
            has_m15_bos=has_m15_bos,
            has_m15_choch=has_m15_choch,
            has_m15_entry_confirmation=has_m15_entry_confirmation,
            has_liquidity_sweep=has_liquidity_sweep,
            min_rr=min_rr,
        )
        coach_result = self.coach(analysis, validation, min_rr)
        return {"analysis": analysis_dict, "validation": validation, "coach": coach_result, "meta": meta}
