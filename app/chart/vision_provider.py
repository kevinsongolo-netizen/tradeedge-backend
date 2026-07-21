"""Pluggable vision AI provider (screenshot-first workflow, Sprint 20).

Reading a chart *image* requires a vision-capable AI model to look at
the picture and estimate what it shows. That's inherently a best-effort
read -- an AI is estimating trend/structure/order-blocks/prices from
pixels, not computing them from real numbers -- so this module is
deliberately isolated behind one small interface (``VisionProvider``)
that the rest of the app depends on, never on a specific AI vendor's
SDK directly.

Sprint 20 rewrite: TradeEdge moved from a fixed, rule-based strategy
(Daily Bias + M15 Order Block/FVG, no fixed SL/TP -- see
``app/_legacy/`` for that engine, kept for reference/possible reuse)
to a screenshot-first workflow. The user's own MT5 indicator already
draws Order Blocks, FVGs, BOS, and CHoCH directly on the chart, and
MT5's own order panel already shows the pending order's exact Entry,
Stop Loss, Take Profit, and R:R -- so one annotated screenshot is a
complete trade decision already made by the trader, not raw material
for an AI to judge against rules. This provider's job changed from
"read the chart so a rule engine can validate it" to "read everything
visible -- structure AND the trader's own numbers -- so the app can
compare this setup against the trader's own trade history instead."

Two implementations ship today:

* ``PlaceholderVisionProvider`` — always active when no vision API key
  is configured. Returns a clearly-labeled mock analysis so the rest of
  the pipeline (Level 2 validation, Level 3 coaching, the UI) can be
  built and tested end-to-end right now, with zero cost and zero
  external dependency.
* ``AnthropicVisionProvider`` — real analysis via Claude's vision
  input, used automatically the moment ``ANTHROPIC_API_KEY`` is set
  (e.g. as a Render environment variable). No other code changes
  required to go from placeholder to real.

Adding a third provider (OpenAI, a self-hosted model, ...) later means
writing one more class here and one line in ``get_vision_provider`` —
nothing else in the app needs to know.

Sprint 20 Phase 6 -- added ``orderBlockFreshness``/``rejectionStrength``/
``fvgSize`` to the schema: three characteristics the trader specifically
asked the AI to learn from (fresh vs. mitigated zones, rejection candle
strength, FVG size) that a vision read can estimate the same way it
already estimates trend/structure/POI type, but weren't captured at
all before this phase.

Sprint 20 Phase 8 ("AI Learning Engine") -- added ``equalHighsNearby``/
``equalLowsNearby``/``bosType``/``touchNumber``: four more
characteristics the trader listed among the full set they want the AI
learning from every screenshot -- feeding
``app/engines/edge_profile_engine.py``'s comprehensive winner/loser
characteristic discovery, not just the earlier hand-picked dimensions.

Sprint 20 Phase 9 ("Confidence-Tiered Reasoning") -- the trader pointed
out (reviewing an actual screenshot side by side with the AI's output)
that three of these reads are fundamentally different from the others:
whether an order block/FVG is already "mitigated" and how "weak" a
rejection candle is are judgment calls a single static frame often
can't fully prove (has this exact zone really been retested before, or
does it just look untested from one angle?) -- yet they were being
asserted with the same flat certainty as directly-labeled facts like
the pair, direction, or entry price. Added ``orderBlockFreshness
Confidence``/``rejectionStrengthConfidence``/``fvgMitigationConfidence``
(0-100, the model's own honest confidence in THAT SPECIFIC judgment,
not the overall ``readConfidence``) so downstream engines
(``app/engines/characteristic_gap_engine.py``) can hedge a
low-confidence interpretation ("Possible concern (38% confidence): ...")
instead of stating it as settled fact. Directly-observed facts (pair,
direction, entry/SL/TP, BOS/CHoCH/OB/premium-discount presence) are
unaffected -- those stay exactly as confident as they were.

Sprint 20 Phase 12 ("Evidence-Based Reasoning") -- the trader's own
framing, after Phase 11 closed the two-independent-reads gap: "I want
to understand how the AI reached each conclusion, not just what it
concluded." Every interpretive field the model produces (trend,
structure, bias, currentPriceContext, liquidity, latestEvent,
fvgStatus, premiumDiscount, poiType, orderBlockFreshness,
rejectionStrength, fvgSize -- see EVIDENCE_FIELDS) now comes with a
matching list of concrete visual evidence bullets in the new
``evidence`` field, e.g. "Bullish FVG mitigated" paired with "Price
closed back inside the gap on the last two candles." This is a direct
extension of Phase 9's own reasoning (never assert a judgment call with
unearned certainty) -- Phase 9 added an honest CONFIDENCE number for
the three hardest judgment calls; Phase 12 adds the actual EVIDENCE
behind every judgment call, so a low or high confidence score is
itself verifiable against what the model says it actually saw, rather
than a bare number the trader has to take on faith. Deliberately NOT
adding new conclusions/fields beyond this (the trader was explicit:
"rather than adding more features, focus on making every AI
explanation evidence-based") -- ``_ensure_evidence_shape`` below only
ever fills in gaps or trims what the model already produces, it never
invents a new interpretation.

Sprint 20 Phase 13 ("Facts vs. Interpretation vs. Confidence") -- the
trader's own framing after seeing Phase 12's evidence bullets: "Right
now, the AI mixes together things it directly sees on the chart with
things it infers... I want to verify its reasoning instead of simply
trusting it." Two additions, both purely additive (nothing from Phase
9/12 was renamed or removed, so every existing consumer -- the
similarity engine, characteristic-gap engine, edge profile engine, the
Phase 11 cache, the Phase 12 evidence UI -- keeps working unchanged):

1. ``detectedLabels`` -- a new, deliberately dumb field: literal
   annotation text visible on the chart (e.g. "Bullish Order Block",
   "BOS"), no judgment attached. This is the FACTS tier the trader
   asked for, sitting alongside the already-factual transcribed fields
   (pair, entry, orderType, ...).
2. ``confidenceBreakdown`` -- extends Phase 9's idea (an honest 0-100
   confidence number for a judgment call) to all twelve EVIDENCE_FIELDS
   instead of just three, and makes each number itself explainable: a
   list of named positive factors and negative factors with their own
   point contributions, e.g. "BOS present (+20)" / "Counter-trend
   liquidity nearby (-10)" -- mirrors the exact same point-weighted-row
   idea ``app/engines/similar_engine.py``'s similarity breakdown
   already uses for "why is this trade X% similar", applied here to
   "why is this conclusion X% confident".

Phase 9's three original flat confidence fields
(``orderBlockFreshnessConfidence``/``rejectionStrengthConfidence``/
``fvgMitigationConfidence``) are NOT replaced -- ``_ensure_confidence_
breakdown_shape`` now derives them FROM ``confidenceBreakdown`` (single
source of truth, model never asked to state the same number twice),
so the two existing engines that read those three flat fields directly
need zero changes and can never drift out of sync with the new
breakdown.

Same honesty discipline as everywhere else in this module: a model's
claimed point values are never re-summed or corrected to force exact
arithmetic (that would mean fabricating a number no one actually
reasoned about) -- they're sanitized for shape/junk only and displayed
as the model's own stated reasoning, not audited math.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any

from app.config import get_settings

# The JSON shape every provider must return — a "best-effort" mirror of
# the deterministic candle engine's output, using the same field names
# so Level 2/3 logic can treat both paths identically. Confidence
# fields here reflect the vision model's own uncertainty about reading
# the image, not trade quality (that's Level 3's job).
VISION_ANALYSIS_SCHEMA_HINT = {
    "trend": "Bullish | Bearish | Ranging",
    "structure": "Bullish | Bearish | Ranging",
    "currentPriceContext": "free text, e.g. 'Inside bullish order block'",
    "liquidity": "free text, e.g. 'Equal highs resting above price'",
    "latestEvent": "free text, e.g. 'Bullish CHOCH detected' or null",
    "fvgStatus": "free text, e.g. 'Bullish FVG mitigated' or null",
    "premiumDiscount": "Premium | Discount | Equilibrium",
    "bias": "BUY | SELL | NONE",
    "readConfidence": "0-100 int — how confident the model is in this visual read",
    # --- Sprint 20: the trader's own trade decision, read off the
    # screenshot's chart labels and MT5 order panel -- not re-derived
    # or judged, just transcribed as precisely as possible.
    "pair": "the traded symbol exactly as shown, e.g. 'XAUUSD' or 'GOLDmicro', or null if not visible",
    "timeframe": "chart timeframe exactly as shown, e.g. 'M15', 'H1', or null if not visible",
    "orderDirection": "BUY | SELL | null — from the pending order/position type (e.g. a Sell Limit or an open sell is SELL)",
    "orderType": "free text, e.g. 'Sell Limit', 'Buy Stop', 'Market', or null if not visible",
    "entry": "number or null — the entry/order price shown on the chart or order panel",
    "stopLoss": "number or null — the stop loss price shown",
    "takeProfit": "number or null — the take profit price shown",
    "riskReward": "number or null — the R:R ratio if labeled directly, otherwise computed from entry/stopLoss/takeProfit if all three are present",
    "lots": "number or null — position size if shown",
    "poiType": "free text describing the point-of-interest label(s) touching the entry, e.g. 'Bearish Order Block' or 'Bullish FVG', or null",
    # --- Sprint 20 Phase 6: three more characteristics traders judge a
    # setup by, that a vision model can estimate from the same image but
    # weren't previously captured at all -- see this module's Phase 6
    # docstring note below.
    "orderBlockFreshness": "Fresh | Mitigated | null -- has price already traded back into the order block/FVG the entry is based on before this entry (Mitigated), or is it untouched since it formed (Fresh)?",
    "orderBlockFreshnessConfidence": "0-100 int -- HONEST confidence in that specific Fresh/Mitigated read, not overall readConfidence. Only score this high if you can actually see clear evidence of a prior retest (a wick or candle body already trading back through the zone); if you're mostly inferring it from the zone's age or general chart feel, score it low (e.g. 30-50).",
    "rejectionStrength": "Strong | Weak | None | null -- how strongly price rejected from the entry zone (a long wick/strong reversal candle = Strong, a weak indecisive candle = Weak, no clear rejection yet = None)",
    "rejectionStrengthConfidence": "0-100 int -- HONEST confidence in that specific Strong/Weak/None read. Score it low (e.g. 30-50) if there's only one recent candle to judge from, or if the rejection is still forming/ambiguous, rather than defaulting to a confident label either way.",
    "fvgSize": "Large | Medium | Small | null -- the fair value gap's size relative to recent candles, if one is visible",
    "fvgMitigationConfidence": "0-100 int -- HONEST confidence that the fair value gap described in fvgStatus is actually mitigated/filled (as opposed to still open) -- low (e.g. 30-50) unless you can see price having clearly traded through the gap already.",
    # --- Sprint 20 Phase 8 ("AI Learning Engine") -- four more
    # characteristics the trader specifically listed as things to learn
    # from, that a vision model can estimate the same way it already
    # estimates freshness/rejection/FVG size above.
    "equalHighsNearby": "true | false | null -- are there visible equal highs (resting liquidity) near price?",
    "equalLowsNearby": "true | false | null -- are there visible equal lows (resting liquidity) near price?",
    "bosType": "Internal | External | null -- if a break of structure is marked, is it an internal (minor swing) or external (major swing) BOS?",
    "touchNumber": "First | Second | Third+ | null -- is this the first, second, or third-or-later time price has touched the order block/FVG the entry is based on?",
    # --- Sprint 20 Phase 12 ("Evidence-Based Reasoning") -- the trader's
    # own framing: "I want to understand how the AI reached each
    # conclusion, not just what it concluded." Every interpretive field
    # above (as opposed to numbers/labels transcribed directly off the
    # chart, like pair/entry/orderType) gets a matching list of short,
    # concrete visual evidence bullets here -- see EVIDENCE_FIELDS and
    # this module's Phase 12 docstring note below for the full
    # rationale and the exact set of fields covered.
    "evidence": {field: "array of short strings -- concrete visual evidence for this specific conclusion, e.g. 'Price closed back inside the gap on the last two candles' -- empty array if there is genuinely nothing to point to" for field in ["trend", "structure", "bias", "currentPriceContext", "liquidity", "latestEvent", "fvgStatus", "premiumDiscount", "poiType", "orderBlockFreshness", "rejectionStrength", "fvgSize"]},
    # --- Sprint 20 Phase 13 ("Facts vs. Interpretation vs. Confidence")
    # -- the trader's own framing: "Right now, the AI mixes together
    # things it directly sees on the chart with things it infers." This
    # is the FACTS side of that split -- literal chart annotation
    # labels as your own MT5 indicator drew them (e.g. "Bullish Order
    # Block", "Bullish FVG", "BOS", "CHoCH", "Discount", "Equal High"),
    # with NO interpretation attached (not "mitigated", not "likely
    # filled" -- just that the label is there). What those labels MEAN
    # stays entirely in the existing interpretive fields above (poiType,
    # fvgStatus, orderBlockFreshness, etc.) and their evidence/
    # confidenceBreakdown below -- this field exists purely so the UI
    # can show an unopinionated "here's what's literally on the chart"
    # list before any AI reasoning about it.
    "detectedLabels": "array of short strings -- ONLY the literal annotation labels/text visible on the chart or order panel (e.g. 'Bullish Order Block', 'Bullish FVG', 'BOS', 'CHoCH', 'Discount', 'Equal High'), never an interpretation or judgment -- if a label isn't literally visible, leave it out rather than inferring it belongs there",
    # --- Sprint 20 Phase 13 continued -- the CONFIDENCE side of the
    # split: "For every interpretation, show why the confidence is what
    # it is." One point-weighted breakdown per EVIDENCE_FIELDS entry,
    # mirroring the same idea the similarity engine already uses for
    # "why is this trade X% similar" (SimilarityBreakdownRow), applied
    # here to "why is this conclusion X% confident" -- positive factors
    # that raise confidence, negative factors that lower it, and the
    # honest final number, so a confidence score is itself verifiable
    # against named reasons instead of an unexplained number.
    "confidenceBreakdown": {
        field: {
            "finalConfidence": "0-100 int -- your honest overall confidence in this specific conclusion",
            "positiveFactors": "array of {reason: short string, points: positive int} -- concrete things that INCREASE your confidence, e.g. {'reason': 'BOS confirms continuation', 'points': 20}",
            "negativeFactors": "array of {reason: short string, points: negative int} -- concrete things that DECREASE your confidence, e.g. {'reason': 'Counter-trend liquidity nearby', 'points': -10}. Empty array if nothing reduces your confidence.",
        }
        for field in ["trend", "structure", "bias", "currentPriceContext", "liquidity", "latestEvent", "fvgStatus", "premiumDiscount", "poiType", "orderBlockFreshness", "rejectionStrength", "fvgSize"]
    },
}

# The exact set of interpretive/judgment fields Phase 12 requires
# evidence for -- everything in the schema above that's an AI READING
# or INTERPRETATION of the chart, not a value transcribed directly off
# a label (pair/timeframe/orderType/orderDirection/entry/stopLoss/
# takeProfit/riskReward/lots/equalHighsNearby/equalLowsNearby/bosType/
# touchNumber are excluded: those are read straight off what's already
# printed on the chart or order panel, not inferred, so there's no
# separate "reasoning" to show -- the transcribed value already IS the
# evidence).
EVIDENCE_FIELDS: tuple[str, ...] = (
    "trend", "structure", "bias", "currentPriceContext", "liquidity",
    "latestEvent", "fvgStatus", "premiumDiscount", "poiType",
    "orderBlockFreshness", "rejectionStrength", "fvgSize",
)

# Never let one field's evidence list balloon into an essay -- a
# handful of concrete bullets is more verifiable (and more readable in
# the UI) than a long, hedging paragraph masquerading as a list.
MAX_EVIDENCE_BULLETS_PER_FIELD = 4

# Sprint 20 Phase 13 -- same 12 fields get a point-weighted confidence
# breakdown as get evidence bullets (one tier deeper: not just WHY a
# conclusion was reached, but WHY that specific confidence number).
CONFIDENCE_FIELDS: tuple[str, ...] = EVIDENCE_FIELDS

# Same reasoning as MAX_EVIDENCE_BULLETS_PER_FIELD -- a handful of named
# factors is more verifiable than an unbounded list of small nudges.
MAX_CONFIDENCE_FACTORS_PER_FIELD = 5

# Legacy Phase 9 flat confidence fields, each mapped to the Phase 13
# confidenceBreakdown key that now supersedes it as the single source
# of truth. _ensure_confidence_breakdown_shape derives these FROM the
# breakdown (never the reverse) so app/engines/characteristic_gap_
# engine.py and app/engines/setup_insight_engine.py -- which already
# read these three flat fields directly -- keep working completely
# unchanged, with no risk of the two ever silently disagreeing.
_LEGACY_CONFIDENCE_FIELD_MAP: dict[str, str] = {
    "orderBlockFreshness": "orderBlockFreshnessConfidence",
    "rejectionStrength": "rejectionStrengthConfidence",
    "fvgStatus": "fvgMitigationConfidence",
}


class VisionProvider(ABC):
    """One method: image bytes in, a Level-1-shaped analysis dict out."""

    name: str = "base"

    @abstractmethod
    async def analyze_screenshot(self, image_bytes: bytes, mime_type: str) -> dict[str, Any]:
        """Returns a dict matching ``VISION_ANALYSIS_SCHEMA_HINT``'s
        keys. Implementations should raise ``VisionProviderError`` (not
        a raw SDK exception) on failure, per the app's error-handling
        convention of engines/providers not knowing about HTTP."""
        raise NotImplementedError


class VisionProviderError(Exception):
    """Raised by any ``VisionProvider`` on failure (bad image, API
    error, malformed model response, ...). Callers (the chart service)
    translate this into a proper API error."""


class PlaceholderVisionProvider(VisionProvider):
    """No API key configured yet. Returns an honestly-labeled mock
    analysis — every field says "placeholder" somewhere so it's never
    mistaken for a real read in the UI or in logs. This exists so the
    full pipeline (upload -> Level 1 -> Level 2 -> Level 3 -> UI) can
    be built, tested, and demoed today, and becomes real the moment
    ``ANTHROPIC_API_KEY`` (or another provider's key) is set — no code
    changes needed anywhere else."""

    name = "placeholder"

    async def analyze_screenshot(self, image_bytes: bytes, mime_type: str) -> dict[str, Any]:
        if not image_bytes:
            raise VisionProviderError("Empty image.")
        return {
            "trend": "Bullish",
            "structure": "Bullish",
            "currentPriceContext": "PLACEHOLDER — no vision API key configured yet. This is not a real chart read.",
            "liquidity": "PLACEHOLDER — equal highs resting above price (example data)",
            "latestEvent": "PLACEHOLDER — bullish CHOCH detected (example data)",
            "fvgStatus": "PLACEHOLDER — bullish FVG mitigated (example data)",
            "premiumDiscount": "Discount",
            "bias": "BUY",
            "readConfidence": 0,
            "pair": "PLACEHOLDER — GOLDmicro (example data)",
            "timeframe": "PLACEHOLDER — M15 (example data)",
            "orderDirection": "BUY",
            "orderType": "PLACEHOLDER — Buy Limit (example data)",
            "entry": None,
            "stopLoss": None,
            "takeProfit": None,
            "riskReward": None,
            "lots": None,
            "poiType": "PLACEHOLDER — Bullish Order Block (example data)",
            "orderBlockFreshness": "Fresh",
            "orderBlockFreshnessConfidence": 80,
            "rejectionStrength": "Strong",
            "rejectionStrengthConfidence": 75,
            "fvgSize": "Medium",
            "fvgMitigationConfidence": 45,
            "equalHighsNearby": True,
            "equalLowsNearby": False,
            "bosType": "External",
            "touchNumber": "First",
            "numberConsistencyWarning": None,
            "evidence": {
                field: [f"PLACEHOLDER — example evidence for {field} (no vision API key configured yet)"]
                for field in EVIDENCE_FIELDS
            },
            "detectedLabels": [
                "PLACEHOLDER — Bullish Order Block (example data)",
                "PLACEHOLDER — Bullish FVG (example data)",
                "PLACEHOLDER — BOS (example data)",
            ],
            "confidenceBreakdown": {
                field: {
                    # Kept consistent with the three legacy flat
                    # confidence fields above (80/75/45) for the fields
                    # that map to one, so a real read's Phase 13
                    # derivation logic (breakdown -> legacy fields) has
                    # an honest placeholder equivalent to compare
                    # against -- neutral 50 for every other field, which
                    # has no pre-existing legacy number to match.
                    "finalConfidence": {"orderBlockFreshness": 80, "rejectionStrength": 75, "fvgStatus": 45}.get(field, 50),
                    "positiveFactors": [{"reason": f"PLACEHOLDER — example positive factor for {field}", "points": 20}],
                    "negativeFactors": [{"reason": f"PLACEHOLDER — example negative factor for {field}", "points": -10}],
                }
                for field in CONFIDENCE_FIELDS
            },
            "provider": self.name,
            "isPlaceholder": True,
        }


def _extract_json_object(text: str) -> dict[str, Any]:
    """Parse the vision model's response as JSON, defensively.

    The prompt tells Claude to respond with ONLY a JSON object, and it
    usually does -- but vision models occasionally still wrap the
    answer in a ```json ... ``` markdown fence, or add a short sentence
    before/after the object despite the instruction. Rather than fail
    the whole analysis on that kind of harmless formatting, strip a
    fence if present and fall back to the first ``{...}`` span in the
    text before giving up.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped[:4].lower() == "json":
            stripped = stripped[4:].strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(stripped[start : end + 1])
    raise json.JSONDecodeError("No JSON object found in vision model response", stripped, 0)


def _reconcile_direction_with_order_type(parsed: dict[str, Any]) -> None:
    """A trader compared Pre-Trade Check and the Chart Analysis Engine
    against the SAME BTCUSD "Buy Limit" screenshot and found one
    correctly said BUY while the other said SELL -- both features call
    the same vision provider, but ``orderDirection`` and ``orderType``
    are two SEPARATE judgment calls the model makes from one image,
    and (being independent guesses) they can disagree with each other
    even on the same screenshot.

    Unlike a genuine number misread -- where either the stop loss or
    the take profit could plausibly be the wrong one, so
    ``_apply_number_sanity_check`` below only WARNS rather than
    guessing which -- ``orderType`` free text directly ENCODES
    direction by definition: a "Buy Limit"/"Buy Stop"/"Buy" order IS a
    BUY, a "Sell Limit"/"Sell Stop"/"Sell" order IS a SELL. There's
    nothing to preserve by trusting a separate, independent
    ``orderDirection`` guess when it contradicts text that already
    settles the question -- this deterministically reconciles
    ``orderDirection`` FROM ``orderType`` whenever ``orderType``
    unambiguously names exactly one side.

    Runs BEFORE ``_apply_number_sanity_check`` so that check's own
    SL/TP-vs-direction validation uses the corrected, self-consistent
    direction -- otherwise a misread direction produces a second,
    entirely spurious "these numbers look inconsistent" warning on
    numbers that were actually fine all along (exactly what the
    trader also saw happen)."""
    order_type = parsed.get("orderType") or ""
    has_buy = re.search(r"\bbuy\b", order_type, re.IGNORECASE) is not None
    has_sell = re.search(r"\bsell\b", order_type, re.IGNORECASE) is not None
    if has_buy and not has_sell:
        parsed["orderDirection"] = "BUY"
    elif has_sell and not has_buy:
        parsed["orderDirection"] = "SELL"
    # orderType mentioning both/neither (e.g. a plain "Market" order,
    # or a garbled read) is genuinely ambiguous -- leave orderDirection
    # exactly as the model reported it, nothing safe to reconcile.


def _apply_number_sanity_check(parsed: dict[str, Any]) -> None:
    """Flag (never silently fix) a stop loss / take profit that lands on
    the wrong side of the entry for the stated direction.

    A vision model reading small price labels off a screenshot will
    occasionally misread a digit -- there's no way to know which number
    is wrong from the image alone, so this doesn't guess a correction.
    It sets ``numberConsistencyWarning`` so the UI can tell the trader
    to double-check the source screenshot instead of quietly trusting a
    read that's internally impossible (e.g. a SELL's stop loss sitting
    below its entry). Also recomputes riskReward deterministically from
    entry/stopLoss/takeProfit when all three are numeric and consistent,
    since that's plain arithmetic Python can do exactly, rather than
    relying on the vision model's own arithmetic.
    """
    parsed["numberConsistencyWarning"] = None

    direction = parsed.get("orderDirection")
    entry = parsed.get("entry")
    sl = parsed.get("stopLoss")
    tp = parsed.get("takeProfit")
    if direction not in ("BUY", "SELL") or not isinstance(entry, (int, float)):
        return

    problems = []
    if isinstance(sl, (int, float)):
        if direction == "SELL" and sl <= entry:
            problems.append("stop loss is below/at entry, but should be above entry for a SELL")
        if direction == "BUY" and sl >= entry:
            problems.append("stop loss is above/at entry, but should be below entry for a BUY")
    if isinstance(tp, (int, float)):
        if direction == "SELL" and tp >= entry:
            problems.append("take profit is above/at entry, but should be below entry for a SELL")
        if direction == "BUY" and tp <= entry:
            problems.append("take profit is below/at entry, but should be above entry for a BUY")

    if problems:
        parsed["numberConsistencyWarning"] = (
            "These numbers look inconsistent with a "
            + direction
            + " order ("
            + "; ".join(problems)
            + ") -- double-check them against the screenshot, this may be a misread digit."
        )
        return

    if isinstance(sl, (int, float)) and isinstance(tp, (int, float)):
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk > 0:
            parsed["riskReward"] = round(reward / risk, 2)


def _ensure_evidence_shape(parsed: dict[str, Any]) -> None:
    """Sprint 20 Phase 12 -- never trust the model's ``evidence`` object
    blindly, same philosophy as every other post-processing step in
    this module. The prompt asks for a bullet list per EVIDENCE_FIELDS
    key, but a vision model can still omit the whole key, omit one
    field's list, return a single string instead of a list, or return a
    list containing non-string junk -- none of that should ever reach
    the UI as-is or make downstream code need to defensively re-check
    every shape.

    Guarantees, after this runs: ``parsed["evidence"]`` is always a
    dict with EXACTLY the keys in EVIDENCE_FIELDS (missing ones default
    to an empty list, never absent entirely), each value is always a
    list of non-empty strings, and each list is capped at
    MAX_EVIDENCE_BULLETS_PER_FIELD so one over-eager field can't turn
    into a wall of text in the UI."""
    raw_evidence = parsed.get("evidence")
    if not isinstance(raw_evidence, dict):
        raw_evidence = {}

    cleaned: dict[str, list[str]] = {}
    for field in EVIDENCE_FIELDS:
        bullets = raw_evidence.get(field)
        if isinstance(bullets, str):
            # The model occasionally collapses a one-item list into a
            # bare string despite the schema hint -- still one valid
            # piece of evidence, not worth discarding over a shape slip.
            bullets = [bullets]
        if not isinstance(bullets, list):
            bullets = []
        clean_bullets = [b.strip() for b in bullets if isinstance(b, str) and b.strip()]
        cleaned[field] = clean_bullets[:MAX_EVIDENCE_BULLETS_PER_FIELD]

    parsed["evidence"] = cleaned


def _clean_confidence_factors(raw_factors: Any, *, force_negative: bool) -> list[dict[str, Any]]:
    """Shared cleanup for one field's positiveFactors or negativeFactors
    list -- every {reason, points} entry must have a non-empty string
    reason and an int points value; ``force_negative`` flips the sign
    of a positive-looking value that landed in negativeFactors (or vice
    versa) rather than dropping an otherwise-valid factor over a sign
    slip, since the model still clearly meant it to reduce/raise
    confidence given which list it put it in."""
    if not isinstance(raw_factors, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for item in raw_factors:
        if not isinstance(item, dict):
            continue
        reason = item.get("reason")
        points = item.get("points")
        if not isinstance(reason, str) or not reason.strip():
            continue
        if isinstance(points, bool) or not isinstance(points, (int, float)):
            continue
        points_int = int(points)
        if force_negative:
            points_int = -abs(points_int)
        else:
            points_int = abs(points_int)
        cleaned.append({"reason": reason.strip(), "points": points_int})
    return cleaned[:MAX_CONFIDENCE_FACTORS_PER_FIELD]


def _ensure_confidence_breakdown_shape(parsed: dict[str, Any]) -> None:
    """Sprint 20 Phase 13 -- never trust the model's
    ``confidenceBreakdown`` object blindly, same philosophy as
    ``_ensure_evidence_shape`` above. Guarantees, after this runs:
    ``parsed["confidenceBreakdown"]`` always has exactly the keys in
    CONFIDENCE_FIELDS, each with an int ``finalConfidence`` (0-100,
    clamped), and ``positiveFactors``/``negativeFactors`` lists of
    clean ``{reason, points}`` dicts (positive/negative sign enforced
    by which list they're in, never re-summed against finalConfidence
    -- see this module's Phase 13 docstring note on why the model's
    stated reasoning is displayed as-is rather than audited math).

    Also derives the three Phase 9 legacy flat confidence fields
    (_LEGACY_CONFIDENCE_FIELD_MAP) FROM this breakdown -- single source
    of truth, so app/engines/characteristic_gap_engine.py and
    app/engines/setup_insight_engine.py (which still read those three
    flat fields directly) can never silently disagree with what's
    actually shown in the UI's confidence breakdown."""
    raw_breakdown = parsed.get("confidenceBreakdown")
    if not isinstance(raw_breakdown, dict):
        raw_breakdown = {}

    cleaned: dict[str, dict[str, Any]] = {}
    for field in CONFIDENCE_FIELDS:
        entry = raw_breakdown.get(field)
        if not isinstance(entry, dict):
            entry = {}

        final_confidence = entry.get("finalConfidence")
        if isinstance(final_confidence, bool) or not isinstance(final_confidence, (int, float)):
            # No usable number from the new breakdown -- fall back to
            # this field's existing legacy flat value if the model (or
            # an older prompt) still supplied one directly, otherwise a
            # neutral, honestly-unremarkable default rather than a
            # confident-looking guess.
            legacy_field = _LEGACY_CONFIDENCE_FIELD_MAP.get(field)
            legacy_value = parsed.get(legacy_field) if legacy_field else None
            final_confidence = legacy_value if isinstance(legacy_value, (int, float)) and not isinstance(legacy_value, bool) else 50
        final_confidence = max(0, min(100, int(final_confidence)))

        cleaned[field] = {
            "finalConfidence": final_confidence,
            "positiveFactors": _clean_confidence_factors(entry.get("positiveFactors"), force_negative=False),
            "negativeFactors": _clean_confidence_factors(entry.get("negativeFactors"), force_negative=True),
        }

    parsed["confidenceBreakdown"] = cleaned

    # Derive the legacy flat fields FROM the cleaned breakdown -- always
    # overwrite, never merely fill a gap, so there is exactly one source
    # of truth going forward and the two can never drift apart.
    for field, legacy_field in _LEGACY_CONFIDENCE_FIELD_MAP.items():
        parsed[legacy_field] = cleaned[field]["finalConfidence"]


class AnthropicVisionProvider(VisionProvider):
    """Real vision analysis via Claude. Only imports/uses the
    ``anthropic`` SDK when actually constructed (i.e. only when an API
    key is present) so the package stays a soft dependency — the app
    runs fine without it installed if you never configure a key."""

    name = "anthropic"

    #: Sprint 22 stability audit -- the Anthropic SDK's own default
    #: timeout is 10 minutes. That's fine for a batch job but not for a
    #: synchronous request a trader is sitting in front of (Pre-Trade
    #: Check / Chart Analysis Engine) -- a slow or hung upstream call
    #: would tie up the request for up to 10 minutes with zero feedback.
    #: The other two external calls this app makes (news calendar,
    #: Cloudinary image upload) both already set an explicit, much
    #: shorter timeout; this brings vision analysis in line with that
    #: same pattern instead of being the one inconsistent exception.
    _REQUEST_TIMEOUT_SECONDS = 45.0

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5") -> None:
        self._api_key = api_key
        self._model = model

    def _prompt(self) -> str:
        return (
            "You are looking at a trader's own MT5 chart screenshot. Their own "
            "indicator has already marked the chart's structure (order blocks, "
            "fair value gaps, BOS, CHoCH, equal highs/lows), and MT5's own order "
            "panel shows their actual pending order or open position with its "
            "exact Entry, Stop Loss, Take Profit, and lot size. Your job is to "
            "read what's already there as precisely as possible -- NOT to invent "
            "a trade or judge whether it's good. Transcribe: overall trend, "
            "market structure, whether price is inside an order block, resting "
            "liquidity (equal highs/lows), the most recent structural event (BOS "
            "or CHOCH), fair value gap status, whether price is in a premium or "
            "discount zone, the traded pair and chart timeframe as labeled, the "
            "order/position type and direction, and the exact Entry/Stop Loss/"
            "Take Profit/lot-size numbers from the order panel or chart labels. "
            "If R:R isn't labeled directly, compute it from Entry/Stop Loss/Take "
            "Profit when all three are readable. Also assess: whether the order "
            "block/FVG the entry is based on has already been retested before "
            "this entry (mitigated) or is still untouched (fresh), how strongly "
            "price rejected from the entry zone (a long reversal wick vs. a weak "
            "indecisive candle vs. no clear rejection), the fair value gap's "
            "size relative to recent candles if one is visible, whether visible "
            "equal highs or equal lows sit near price, whether a marked BOS is "
            "an internal (minor swing) or external (major swing) break, and "
            "whether this is the first, second, or third-or-later time price "
            "has touched the order block/FVG. "
            "IMPORTANT -- be honest about your own confidence in the three "
            "judgment calls above (order block freshness, rejection strength, "
            "FVG mitigation): these require inferring things a single static "
            "image often can't fully prove (e.g. whether this exact zone was "
            "genuinely retested before, not just how it looks from one angle). "
            "Only report high confidence (70+) when you can point to clear "
            "visible evidence (a candle body/wick already trading back through "
            "the zone, a long obvious reversal wick, etc.); otherwise report a "
            "realistic lower confidence (30-60) rather than defaulting to a "
            "confident-sounding label you can't actually back up. "
            "ALSO IMPORTANT -- never state an interpretation without backing "
            "it up. For every field listed in \"evidence\" below (trend, "
            "structure, bias, currentPriceContext, liquidity, latestEvent, "
            "fvgStatus, premiumDiscount, poiType, orderBlockFreshness, "
            "rejectionStrength, fvgSize), list the SPECIFIC, concrete visual "
            "evidence from THIS screenshot that led you to that conclusion -- "
            "e.g. 'Price closed back inside the gap on the last two candles' "
            "or 'Long lower wick rejecting the order block zone', not vague "
            "restatements like 'the chart shows this' or 'it looks bullish'. "
            "1-3 bullets per field is usually enough; use an empty array "
            "for a field if you genuinely have nothing concrete to point to "
            "(and let that honestly show up as lower confidence, rather than "
            "inventing evidence to justify a conclusion you're not sure of). "
            "ALSO IMPORTANT -- keep FACTS separate from INTERPRETATION. "
            "\"detectedLabels\" must contain ONLY the literal annotation text "
            "actually visible on the chart (e.g. \"Bullish Order Block\", "
            "\"Bullish FVG\", \"BOS\", \"CHoCH\", \"Discount\", \"Equal High\") -- "
            "if your own indicator drew a label, it belongs here verbatim, "
            "with zero judgment attached (never write \"mitigated\" or "
            "\"likely filled\" in this list -- that's interpretation, which "
            "belongs in fvgStatus/orderBlockFreshness and their evidence, "
            "not here). Leave a label out entirely if it isn't literally on "
            "the chart -- do not infer one belongs there. "
            "ALSO IMPORTANT -- for \"confidenceBreakdown\", give the same "
            "twelve fields listed under \"evidence\" a point-weighted "
            "breakdown of WHY that specific confidence number is what it is: "
            "positiveFactors for concrete things raising your confidence "
            "(e.g. {\"reason\": \"BOS confirms continuation\", \"points\": 20}), "
            "negativeFactors for concrete things lowering it (e.g. "
            "{\"reason\": \"Counter-trend liquidity nearby\", \"points\": -10}). "
            "Use small, honest point values (roughly 10-25 per factor) that "
            "should roughly explain how you arrived at finalConfidence -- this "
            "doesn't need to be exact arithmetic, but it should genuinely "
            "reflect your reasoning, not be invented after the fact to "
            "justify a number you already picked. Empty arrays are fine when "
            "there's nothing specific to list either way. "
            "Respond with ONLY a JSON object with exactly these keys: "
            f"{json.dumps(VISION_ANALYSIS_SCHEMA_HINT)}. "
            "If you cannot confidently determine a field from the image, use "
            "null (for numeric or optional text fields), \"Ranging\" for "
            "trend/structure, \"NONE\" for bias/orderDirection, and a low "
            "readConfidence. Do not include any text outside the JSON object."
        )

    async def analyze_screenshot(self, image_bytes: bytes, mime_type: str) -> dict[str, Any]:
        try:
            import anthropic  # imported lazily — soft dependency, see class docstring
        except ImportError as exc:  # pragma: no cover - exercised only without the package installed
            raise VisionProviderError(
                "The 'anthropic' package is not installed. Add it to requirements.txt to use real vision analysis."
            ) from exc

        text = ""
        try:
            client = anthropic.AsyncAnthropic(api_key=self._api_key, timeout=self._REQUEST_TIMEOUT_SECONDS)
            encoded = base64.standard_b64encode(image_bytes).decode("utf-8")
            response = await client.messages.create(
                model=self._model,
                # Sprint 20 Phase 12/13: evidence bullets AND a
                # point-weighted confidence breakdown for 12 fields add
                # meaningfully to the response length -- 1024 was
                # occasionally tight even before Phase 12, and
                # truncation mid-JSON is exactly what breaks
                # _extract_json_object.
                max_tokens=3072,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {"type": "base64", "media_type": mime_type, "data": encoded},
                            },
                            {"type": "text", "text": self._prompt()},
                        ],
                    }
                ],
            )
            text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
            parsed = _extract_json_object(text)
        except json.JSONDecodeError as exc:
            # Claude is told to respond with ONLY JSON, but vision models
            # sometimes still wrap it in a ```json fence or add a stray
            # sentence -- _extract_json_object() already tries to recover
            # from that, so getting here means the response genuinely
            # wasn't parseable. Include a snippet of the raw response so
            # this is diagnosable from the API error alone, not just
            # reproducible by re-running the same screenshot.
            snippet = text[:300].replace("\n", " ")
            raise VisionProviderError(
                f"Vision model did not return valid JSON. Raw response started with: {snippet!r}"
            ) from exc
        except VisionProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - any SDK/network failure becomes a VisionProviderError
            raise VisionProviderError(f"Vision API call failed: {exc}") from exc

        parsed.setdefault("provider", self.name)
        parsed["isPlaceholder"] = False
        _reconcile_direction_with_order_type(parsed)
        _apply_number_sanity_check(parsed)
        _ensure_evidence_shape(parsed)
        _ensure_confidence_breakdown_shape(parsed)
        return parsed


class CachingVisionProvider(VisionProvider):
    """A trader compared Pre-Trade Check and the Chart Analysis Engine
    against the SAME screenshot and found the two features' free-text
    descriptions of the identical chart didn't quite match each other
    ("Multiple Bullish FVGs marked on chart, appearing mitigated" vs.
    "Bullish FVG marked and visible on chart") -- even after Phase 10's
    orderDirection/orderType reconciliation fixed the more serious
    BUY/SELL contradiction. Both features already route through the
    same endpoint and the same get_vision_provider() factory, so the
    remaining cause isn't two different code paths -- it's that each
    upload triggers its OWN independent, non-deterministic vision API
    call, even when the image bytes are byte-for-byte identical.

    This wraps an inner provider with a content-addressed cache keyed
    by a SHA-256 hash of the image bytes (not by session/trade/endpoint,
    since a screenshot's content -- not who's asking about it -- is
    what should determine whether it's "the same analysis"). Every
    module downstream of get_vision_provider() -- Pre-Trade Check,
    Chart Analysis Engine, Journal, Similarity Engine, Machine
    Learning -- now reads the SAME cached extraction ("fingerprint")
    for the same screenshot, so they can never again disagree about
    what the AI detected in it.

    A screenshot's content never changes once uploaded, so this could
    justifiably never expire -- but a generous TTL still bounds memory
    growth on a long-running process over weeks/months of usage
    without ever affecting normal usage (re-analyzing the same
    screenshot minutes or hours apart, which is the actual scenario
    that prompted this fix).

    Mirrors the same wrapper + cache-clearing-factory pattern already
    used by CachingCalendarProvider in app/news/calendar_provider.py."""

    def __init__(self, inner: VisionProvider, ttl_seconds: int = 24 * 3600) -> None:
        self._inner = inner
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self.name = inner.name

    async def analyze_screenshot(self, image_bytes: bytes, mime_type: str) -> dict[str, Any]:
        key = hashlib.sha256(image_bytes).hexdigest()
        cached = self._cache.get(key)
        now = time.monotonic()
        if cached is not None and (now - cached[0]) < self._ttl:
            # Defensive copy: callers may mutate the returned dict (e.g.
            # setdefault, further enrichment) and must never poison the
            # cached entry shared across every module reading it.
            return dict(cached[1])
        result = await self._inner.analyze_screenshot(image_bytes, mime_type)
        self._cache[key] = (now, result)
        return dict(result)


@lru_cache
def get_vision_provider() -> VisionProvider:
    """Factory: real provider if a key is configured, placeholder
    otherwise. This is the single switch point — nothing else in the
    app imports a concrete provider class directly.

    @lru_cache makes this return the SAME CachingVisionProvider instance
    (and therefore the same cache dict) across every request within one
    running process -- without it, a fresh, empty cache would be built
    on every single call, defeating the whole point. This mirrors
    get_calendar_provider()'s identical, already-working pattern."""
    settings = get_settings()
    api_key = getattr(settings, "anthropic_api_key", None)
    if api_key:
        return CachingVisionProvider(AnthropicVisionProvider(api_key=api_key))
    return PlaceholderVisionProvider()
