"""Pluggable vision AI provider (Chart Analysis Engine — Level 1,
"screenshot" path).

Reading a chart *image* (as opposed to real OHLC numbers, see
``candle_smc_engine.py``) requires a vision-capable AI model to look at
the picture and estimate what it shows. That's inherently a best-effort
read — an AI is estimating trend/structure/order-blocks from pixels,
not computing them from real prices — so this module is deliberately
isolated behind one small interface (``VisionProvider``) that the rest
of the app depends on, never on a specific AI vendor's SDK directly.

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
            "provider": self.name,
            "isPlaceholder": True,
        }


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
            "You are a Smart Money Concepts (SMC) chart analyst. Look at this "
            "forex/trading chart screenshot and identify: overall trend, market "
            "structure, whether current price is inside an order block, resting "
            "liquidity (equal highs/lows), the most recent structural event (BOS "
            "or CHOCH), fair value gap status, and whether price is in a premium "
            "or discount zone relative to the visible range. "
            "Respond with ONLY a JSON object with exactly these keys: "
            f"{json.dumps(VISION_ANALYSIS_SCHEMA_HINT)}. "
            "If you cannot confidently determine a field from the image, use "
            "null for text fields, \"Ranging\" for trend/structure, \"NONE\" for "
            "bias, and a low readConfidence. Do not include any text outside the "
            "JSON object."
        )

    async def analyze_screenshot(self, image_bytes: bytes, mime_type: str) -> dict[str, Any]:
        try:
            import anthropic  # imported lazily — soft dependency, see class docstring
        except ImportError as exc:  # pragma: no cover - exercised only without the package installed
            raise VisionProviderError(
                "The 'anthropic' package is not installed. Add it to requirements.txt to use real vision analysis."
            ) from exc

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
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise VisionProviderError("Vision model did not return valid JSON.") from exc
        except VisionProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - any SDK/network failure becomes a VisionProviderError
            raise VisionProviderError(f"Vision API call failed: {exc}") from exc

        parsed.setdefault("provider", self.name)
        parsed["isPlaceholder"] = False
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
