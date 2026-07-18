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
"""
from __future__ import annotations

import base64
import json
from abc import ABC, abstractmethod
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
    "rejectionStrength": "Strong | Weak | None | null -- how strongly price rejected from the entry zone (a long wick/strong reversal candle = Strong, a weak indecisive candle = Weak, no clear rejection yet = None)",
    "fvgSize": "Large | Medium | Small | null -- the fair value gap's size relative to recent candles, if one is visible",
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
            "rejectionStrength": "Strong",
            "fvgSize": "Medium",
            "numberConsistencyWarning": None,
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


class AnthropicVisionProvider(VisionProvider):
    """Real vision analysis via Claude. Only imports/uses the
    ``anthropic`` SDK when actually constructed (i.e. only when an API
    key is present) so the package stays a soft dependency — the app
    runs fine without it installed if you never configure a key."""

    name = "anthropic"

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
            "indecisive candle vs. no clear rejection), and the fair value gap's "
            "size relative to recent candles if one is visible. "
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
            client = anthropic.AsyncAnthropic(api_key=self._api_key)
            encoded = base64.standard_b64encode(image_bytes).decode("utf-8")
            response = await client.messages.create(
                model=self._model,
                max_tokens=1024,
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
        _apply_number_sanity_check(parsed)
        return parsed


def get_vision_provider() -> VisionProvider:
    """Factory: real provider if a key is configured, placeholder
    otherwise. This is the single switch point — nothing else in the
    app imports a concrete provider class directly."""
    settings = get_settings()
    api_key = getattr(settings, "anthropic_api_key", None)
    if api_key:
        return AnthropicVisionProvider(api_key=api_key)
    return PlaceholderVisionProvider()
