"""Normalizes both Level-1 reading paths into the canonical
``ChartAnalysis`` shape (app.schemas.chart) so Level 2 (trade
validation) and Level 3 (AI coach) work identically regardless of
whether the read came from real candle math or a vision AI's estimate
of a screenshot.
"""
from __future__ import annotations

from typing import Any

from app.chart.candle_smc_engine import SmcAnalysis


def _zone_dict(kind: str, zone_type: str, high: float, low: float, mitigated: bool, time: str | None = None) -> dict:
    return {
        "kind": kind,
        "zoneType": zone_type,
        "high": high,
        "low": low,
        "mitigated": mitigated,
        "time": time,
    }


def from_candle_analysis(smc: SmcAnalysis) -> dict[str, Any]:
    """``SmcAnalysis`` (candle_smc_engine.py) -> canonical ChartAnalysis dict."""
    zones: list[dict] = []
    for ob in smc.order_blocks:
        zones.append(_zone_dict(ob.kind, "Order Block", ob.high, ob.low, ob.mitigated, ob.time))
    for gap in smc.fair_value_gaps:
        zones.append(
            _zone_dict(gap.kind, "Fair Value Gap", gap.top, gap.bottom, gap.mitigated, None)
        )

    if smc.price_in_order_block is not None:
        ob = smc.price_in_order_block
        current_price_context = f"Inside {ob.kind.capitalize()} Order Block ({ob.low:.5f}-{ob.high:.5f})"
    else:
        current_price_context = "Not currently inside any identified order block"

    liquidity_parts = []
    if smc.equal_highs:
        liquidity_parts.append(f"Equal highs resting above price ({len(smc.equal_highs)} cluster(s))")
    if smc.equal_lows:
        liquidity_parts.append(f"Equal lows resting below price ({len(smc.equal_lows)} cluster(s))")
    liquidity = "; ".join(liquidity_parts) if liquidity_parts else "No clear equal-highs/equal-lows liquidity detected"

    latest_event = None
    if smc.latest_event is not None:
        latest_event = f"{smc.latest_event.direction.capitalize()} {smc.latest_event.kind} detected"

    fvg_status = None
    bias_side = "bullish" if smc.bias == "BUY" else "bearish" if smc.bias == "SELL" else None
    nearest_fvg = smc.nearest_unmitigated_fvg_bullish if bias_side == "bullish" else smc.nearest_unmitigated_fvg_bearish
    if nearest_fvg is not None:
        fvg_status = f"{nearest_fvg.kind.capitalize()} FVG unmitigated ({nearest_fvg.bottom:.5f}-{nearest_fvg.top:.5f})"
    elif smc.fair_value_gaps:
        last_gap = smc.fair_value_gaps[-1]
        fvg_status = f"{last_gap.kind.capitalize()} FVG {'mitigated' if last_gap.mitigated else 'unmitigated'}"

    entry_zone = None
    nearest_ob = smc.nearest_unmitigated_ob_bullish if bias_side == "bullish" else smc.nearest_unmitigated_ob_bearish
    if nearest_ob is not None:
        entry_zone = _zone_dict(nearest_ob.kind, "Order Block", nearest_ob.high, nearest_ob.low, nearest_ob.mitigated, nearest_ob.time)
    elif nearest_fvg is not None:
        entry_zone = _zone_dict(nearest_fvg.kind, "Fair Value Gap", nearest_fvg.top, nearest_fvg.bottom, nearest_fvg.mitigated)

    notes: list[str] = []
    if len(smc.swing_highs) < 3 or len(smc.swing_lows) < 3:
        notes.append("Limited swing history available — trend/structure read may firm up with more candles.")

    return {
        "source": "candles",
        "trend": smc.trend,
        "structure": smc.structure,
        "currentPriceContext": current_price_context,
        "liquidity": liquidity,
        "latestEvent": latest_event,
        "fvgStatus": fvg_status,
        "premiumDiscount": smc.premium_discount,
        "bias": smc.bias,
        "confidence": 92,  # deterministic math — high read-confidence by construction
        "zones": zones,
        "entryZone": entry_zone,
        "notes": notes,
        "isPlaceholder": False,
    }


def from_vision_analysis(vision: dict[str, Any]) -> dict[str, Any]:
    """Vision provider's raw dict (app.chart.vision_provider) ->
    canonical ChartAnalysis dict. The vision path can't hand back
    precise numeric zones from a picture alone, so ``zones``/
    ``entryZone`` stay empty — Level 2 knows to skip exact
    entry/SL/TP math for screenshot-sourced analyses and says so."""
    notes = ["Read from a chart screenshot via AI vision — treat exact price levels as approximate, not exact."]
    if vision.get("isPlaceholder"):
        notes.insert(0, "PLACEHOLDER DATA — no vision API key is configured yet, this is example output only.")

    return {
        "source": "screenshot",
        "trend": vision.get("trend", "Ranging"),
        "structure": vision.get("structure", "Ranging"),
        "currentPriceContext": vision.get("currentPriceContext") or "Not determined from image",
        "liquidity": vision.get("liquidity") or "Not determined from image",
        "latestEvent": vision.get("latestEvent"),
        "fvgStatus": vision.get("fvgStatus"),
        "premiumDiscount": vision.get("premiumDiscount", "Equilibrium"),
        "bias": vision.get("bias", "NONE"),
        "confidence": int(vision.get("readConfidence") or 0),
        "zones": [],
        "entryZone": None,
        "notes": notes,
        "isPlaceholder": bool(vision.get("isPlaceholder", False)),
    }
