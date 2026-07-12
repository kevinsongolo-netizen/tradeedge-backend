"""Plain-language explanation + confidence scoring (Chart Analysis
Engine — Level 3, "AI Trading Coach").

Takes a ``ChartAnalysis`` (Level 1) and a trade-validation dict (Level
2, see ``app.chart.trade_validator.validate_trade``) and explains the
decision in full sentences — never just "Buy" or "Sell" on their own,
per the spec's explicit requirement. Pure function, no I/O.
"""
from __future__ import annotations

from app.schemas.chart import ChartAnalysis


def _trend_quality(analysis: ChartAnalysis, direction: str | None) -> int:
    if direction is None:
        return 20
    aligned = (direction == "buy" and analysis.trend == "Bullish") or (
        direction == "sell" and analysis.trend == "Bearish"
    )
    return 90 if aligned else 15


def _poi_quality(analysis: ChartAnalysis) -> int:
    if analysis.entry_zone is not None and not analysis.entry_zone.mitigated:
        return 90
    context = (analysis.current_price_context or "").lower()
    if "inside" in context:
        return 70
    return 25


def _liquidity_quality(analysis: ChartAnalysis) -> int:
    liquidity = (analysis.liquidity or "").lower()
    if "no clear" in liquidity or "not determined" in liquidity:
        return 30
    return 85


def _bos_quality(analysis: ChartAnalysis) -> int:
    event = (analysis.latest_event or "").lower()
    if "bos" in event:
        return 90
    if event:
        return 40
    return 20


def _choch_quality(analysis: ChartAnalysis) -> int:
    event = (analysis.latest_event or "").lower()
    if "choch" in event:
        return 90
    if event:
        return 40
    return 20


def _fvg_quality(analysis: ChartAnalysis) -> int:
    fvg = (analysis.fvg_status or "").lower()
    if "mitigated" in fvg and "unmitigated" not in fvg:
        return 90
    if "unmitigated" in fvg:
        return 60
    return 30


def _rr_quality(effective_rr: float | None, min_rr: float) -> int:
    if effective_rr is None:
        return 20
    if effective_rr >= min_rr + 1:
        return 100
    if effective_rr >= min_rr:
        return 70
    return 30


def build_confidence_breakdown(analysis: ChartAnalysis, validation: dict, min_rr: float = 2.0) -> dict:
    direction = validation.get("direction")
    trend_alignment = _trend_quality(analysis, direction)
    poi_quality = _poi_quality(analysis)
    liquidity_quality = _liquidity_quality(analysis)
    bos_quality = _bos_quality(analysis)
    choch_quality = _choch_quality(analysis)
    fvg_quality = _fvg_quality(analysis)
    rr_quality = _rr_quality(validation.get("riskReward"), min_rr)

    components = [trend_alignment, poi_quality, liquidity_quality, bos_quality, choch_quality, fvg_quality, rr_quality]
    overall = round(sum(components) / len(components))

    return {
        "trendAlignment": trend_alignment,
        "poiQuality": poi_quality,
        "liquidityQuality": liquidity_quality,
        "bosQuality": bos_quality,
        "chochQuality": choch_quality,
        "fvgQuality": fvg_quality,
        "rrQuality": rr_quality,
        "overall": overall,
    }


def explain(analysis: ChartAnalysis, validation: dict, min_rr: float = 2.0) -> dict:
    direction = validation.get("direction")
    is_valid = validation.get("tradeStatus") == "VALID"
    confidence = build_confidence_breakdown(analysis, validation, min_rr)

    explanation: list[str] = []

    if is_valid and direction is not None:
        headline = f"{direction.upper()} ANALYSIS"
        explanation.append(f"The H4 trend is {analysis.trend.lower()}.")
        explanation.append(f"{analysis.current_price_context}.")
        if analysis.liquidity and "no clear" not in analysis.liquidity.lower():
            explanation.append(f"{analysis.liquidity}.")
        if analysis.latest_event:
            explanation.append(f"A {analysis.latest_event.lower()} formed.")
        if analysis.fvg_status:
            explanation.append(f"{analysis.fvg_status}.")
        explanation.append("The setup follows the higher timeframe trend.")
        rr = validation.get("riskReward")
        if rr is not None:
            explanation.append(f"Risk Reward is 1:{rr:.1f}.")
        if validation.get("reasonsFailed"):
            for reason in validation["reasonsFailed"]:
                explanation.append(reason.lstrip("✗ ").strip() + ".")
        else:
            explanation.append("No obvious conflicts are detected.")
        recommendation = direction.upper()
    else:
        headline = "NO TRADE"
        pd = analysis.premium_discount
        bias_word = "buys" if direction == "buy" else "sells" if direction == "sell" else "a trade"
        explanation.append(f"Price is trading in {pd.lower()} while looking for {bias_word}." if pd != "Equilibrium" else "Price is near equilibrium with no clear edge yet.")
        for reason in validation.get("reasonsFailed", []):
            explanation.append(reason.lstrip("✗ ").strip() + ".")
        if not validation.get("reasonsFailed"):
            explanation.append("The setup does not currently meet the minimum trade criteria.")
        explanation.append("Wait for confirmation.")
        recommendation = "WAIT"

    return {
        "headline": headline,
        "explanation": explanation,
        "confidence": confidence,
        "recommendation": recommendation,
    }
