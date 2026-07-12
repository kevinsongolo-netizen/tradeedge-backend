"""Reason Engine — port of ``js/reason_engine.js``.

Converts a rule-engine check outcome into human-readable text. Pure
function, no I/O — templates are ported verbatim from the JS version
(Section 6 porting rule #1: casing/text preserved).
"""
from __future__ import annotations

from typing import Any, Callable

Context = dict[str, Any]
TemplateFn = Callable[[Context], str]

REASON_ENGINE_VERSION = "6.0"


def _rr_text(prefix: str, ctx: Context) -> str:
    # JS: ctx.rrVal.toFixed(2) -> Python f"{value:.2f}"
    rr_val = ctx.get("rrVal", 0) or 0
    return f"{prefix} ({rr_val:.2f}R)"


REASON_TEMPLATES: dict[str, dict[str, TemplateFn]] = {
    "h4Trend": {
        "pass": lambda ctx: f"H4 trend recorded ({ctx.get('h4Trend')})",
        "fail": lambda ctx: "H4 trend is missing",
    },
    "h4Poi": {
        "pass": lambda ctx: f"H4 point of interest recorded ({ctx.get('h4PoiType')})",
        "fail": lambda ctx: "H4 point of interest is missing",
    },
    "premiumDiscount": {
        "pass": lambda ctx: f"Premium/discount context recorded ({ctx.get('premiumDiscount')})",
        "fail": lambda ctx: "Premium/discount context is missing",
    },
    "m15Confirmation": {
        "pass": lambda ctx: f"M15 confirmation present ({', '.join(ctx.get('m15Confirmations') or [])})",
        "fail": lambda ctx: "M15 confirmation is missing",
    },
    "bos": {
        "pass": lambda ctx: "BOS confirmation present",
        "fail": lambda ctx: "BOS confirmation is missing",
    },
    "choch": {
        "pass": lambda ctx: "CHOCH confirmation present",
        "fail": lambda ctx: "CHOCH confirmation is missing",
    },
    "liquiditySweep": {
        "pass": lambda ctx: "Liquidity sweep confirmation present",
        "fail": lambda ctx: "Liquidity sweep confirmation is missing",
    },
    "session": {
        "pass": lambda ctx: f"Session recorded ({ctx.get('session')})",
        "fail": lambda ctx: "Trading session is missing",
    },
    "rr": {
        "pass": lambda ctx: _rr_text("Risk/reward meets target", ctx),
        "partial": lambda ctx: _rr_text("Risk/reward is acceptable but below target", ctx),
        "fail": lambda ctx: "Risk/reward is missing or too low",
    },
    "news": {
        "pass": lambda ctx: f"News risk acceptable ({ctx.get('news') or 'None'})",
        "partial": lambda ctx: "Medium-impact news risk present",
        "fail": lambda ctx: "High-impact news risk present",
    },
    "confidence": {
        "pass": lambda ctx: f"Confidence recorded ({ctx.get('confidence')}/100)",
        "partial": lambda ctx: f"Confidence is low ({ctx.get('confidence')}/100)",
        "fail": lambda ctx: "Confidence is missing",
    },
    "followedPlan": {
        "pass": lambda ctx: "Trade plan followed",
        "partial": lambda ctx: "Trade plan partially followed",
        "fail": lambda ctx: "Trade plan not followed",
    },
}


def generate_reason(rule_key: str, outcome: str, context: Context | None = None) -> str:
    """generateReason(ruleKey, outcome, context)

    ``outcome`` is one of 'pass' | 'partial' | 'fail'. Falls back to the
    'fail' template if the requested outcome has no template (mirrors
    the JS ``template[outcome] || template.fail``).
    """
    template = REASON_TEMPLATES.get(rule_key)
    if not template:
        return ""
    fn = template.get(outcome) or template.get("fail")
    if fn is None:
        return ""
    return fn(context or {})
