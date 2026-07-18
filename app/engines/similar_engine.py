"""Similar Trade Engine.

``search_similar_legacy`` is a straight port of ``js/similar_trade_engine.js``
(binary matching — kept for regression comparisons per Section 6's
mapping table). ``search_similar`` is the Sprint 6 upgrade: weighted,
graded similarity per Section 7 of the architecture spec.

Sprint 20 Phase 4 -- dimension coverage review against the trader's own
"complete trade fingerprint" list (pair, direction, OB type, FVG,
BOS/CHoCH structure, premium/discount location, session, volatility,
stop size, target size, chart structure):

  - pair, direction, session, stop size (stopDistancePct), target size
    (targetDistancePct) -- already covered (Sprint 6 / Phase 2).
  - OB type -- covered by h4PoiType (the POI label read off the chart,
    e.g. "Bullish Order Block").
  - BOS/CHoCH structure -- covered by the bos/choch tag dimensions.
  - premium/discount location -- covered by premiumDiscount.
  - FVG -- NEW this phase (``fvg``): previously only implicit inside
    h4PoiType when the POI label itself said "FVG"; now its own
    boolean-presence dimension exactly like bos/choch/liquiditySweep.
  - order type (market/limit/stop) -- NEW this phase (``orderType``):
    bucketed from the free-text order type MT5/the vision read
    supplies, ignoring the direction word it also contains (direction
    is already its own separate dimension).
  - chart structure -- partially covered via h4Trend (the vision read's
    "trend" field); the vision schema's separate "structure" field
    (Bullish/Bearish/Ranging) isn't currently mapped into a candidate at
    all and would need its own dimension to add real signal beyond
    h4Trend -- left out of this phase as a smaller, lower-value gap.
  - volatility -- confirmed infeasible earlier in Phase 4 planning: no
    OHLC/ATR data is stored per trade to compute it from, and the
    trader agreed to skip it rather than fake a number.
"""
from __future__ import annotations

import math
from typing import Any

SIMILAR_TRADE_VERSION = "6.0"

# --- Legacy (Sprint 5) binary-match weights --------------------------------
LEGACY_SIMILAR_TRADE_WEIGHTS: dict[str, float] = {
    "pair": 14,
    "direction": 10,
    "asset": 8,
    "session": 10,
    "trend": 10,
    "poi": 12,
    "bos": 8,
    "choch": 8,
    "liquiditySweep": 8,
    "rr": 12,
    "confidence": 6,
}
LEGACY_MIN_PERCENT = 50

# --- Weighted-v1 (Sprint 6) feature weights (Section 7.3) ------------------
DEFAULT_SIMILARITY_WEIGHTS: dict[str, float] = {
    "pair": 14,
    "direction": 10,
    "asset": 8,
    "session": 10,
    "h4Trend": 10,
    "h4PoiType": 12,
    "premiumDiscount": 4,
    "bos": 6,
    "choch": 6,
    "liquiditySweep": 6,
    # Sprint 20 Phase 4 -- FVG presence as its own dimension (was
    # previously only implicitly covered when the POI label itself
    # mentioned FVG) -- same weight/mechanism as the other 3 structural
    # tags above.
    "fvg": 6,
    "news": 3,
    "rr": 6,
    "confidence": 3,
    "lots": 1,
    "entryProximity": 1,
    # Sprint 20 Phase 2 -- stop/target placement as their OWN dimensions,
    # not just folded into the combined R:R ratio. Two setups can share
    # the exact same R:R (say 2.0) with wildly different risk sizing --
    # a 0.1%-of-price stop feels and behaves nothing like a 5%-of-price
    # stop, even at identical R:R -- so comparing them separately lets
    # "similar setups" also mean "similarly-sized stop/target", which is
    # what a trader actually means by "how did I place my stop/TP here
    # before."
    "stopDistancePct": 5,
    "targetDistancePct": 5,
    # Sprint 20 Phase 4 -- market vs. limit vs. stop order is part of the
    # "complete trade fingerprint" the trader asked for. A modest weight
    # (similar to premiumDiscount) -- it's a real distinguishing feature
    # of a setup (did you chase price or wait for it to come to you?) but
    # shouldn't dominate direction/pair/POI, which say more about the
    # setup itself.
    "orderType": 3,
}

_NEWS_RANK = {"None": 0, "Low": 1, "Medium": 2, "High": 3}


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tags(entry: dict) -> list[str]:
    value = entry.get("m15Confirmations")
    return value if isinstance(value, list) else []


# Sprint 20 Phase 4 -- orderType is free text off the vision read/MT5
# order panel ("Buy Limit", "Sell Stop", "Market", ...). Direction is
# already its own dimension, so comparing the RAW string would double
# count it (and penalize a "Buy Limit" vs "Sell Limit" match that's
# otherwise identical in what actually matters here: did you chase
# price, wait for a pullback, or place a stop order beyond it). Bucket
# down to Market / Limit / Stop before comparing.
def _order_type_category(value: Any) -> str | None:
    if not value:
        return None
    v = str(value).lower()
    if "market" in v:
        return "Market"
    if "limit" in v:
        return "Limit"
    if "stop" in v:
        return "Stop"
    return None


def _order_type_similarity(a: Any, b: Any) -> float:
    return _cat_equal(_order_type_category(a), _order_type_category(b))


def normalize_similarity_weights(weights: dict[str, float] | None = None) -> dict[str, float]:
    """Rescales a (possibly partial) weight override so the total is 100,
    same normalization style as the rule engine (Section 7.3)."""
    merged = {**DEFAULT_SIMILARITY_WEIGHTS, **(weights or {})}
    total = sum(float(v) or 0 for v in merged.values()) or 1
    return {k: (float(v) or 0) / total * 100 for k, v in merged.items()}


# --- Weighted-v1 per-feature similarity functions S_f(a, b) -> [0, 1] ------


def _cat_equal(a: Any, b: Any) -> float:
    return 1.0 if a is not None and b is not None and a == b else 0.0


def _pair_equal(a: Any, b: Any) -> float:
    if not a or not b:
        return 0.0
    return 1.0 if str(a).upper() == str(b).upper() else 0.0


def _bool_presence(tag: str, a_tags: list[str], b_tags: list[str]) -> float:
    return 1.0 if (tag in a_tags) == (tag in b_tags) and tag in a_tags else 0.0


def _news_similarity(a: Any, b: Any) -> float:
    ra, rb = _NEWS_RANK.get(a), _NEWS_RANK.get(b)
    if ra is None or rb is None:
        return 0.0
    return max(0.0, 1 - abs(ra - rb) / 3)


def _gaussian(a: float, b: float, sigma: float) -> float:
    return math.exp(-(((a - b) / sigma) ** 2))


def _rr_similarity(a: Any, b: Any) -> float:
    av, bv = _num(a), _num(b)
    if av is None or bv is None:
        return 0.0
    return _gaussian(av, bv, 0.75)


def _confidence_similarity(a: Any, b: Any) -> float:
    av, bv = _num(a), _num(b)
    if av is None or bv is None:
        return 0.0
    return _gaussian(av, bv, 15)


def _lots_similarity(a: Any, b: Any) -> float:
    av, bv = _num(a), _num(b)
    if not av or not bv or av <= 0 or bv <= 0:
        return 0.0
    return _gaussian(math.log10(av), math.log10(bv), 0.5)


def _stop_distance_pct(entry: Any, sl: Any) -> float | None:
    """Stop-loss distance as a percentage of entry price -- how "tight"
    or "wide" the stop is, independent of R:R (two trades can share the
    same R:R with very differently sized stops)."""
    e, s = _num(entry), _num(sl)
    if e is None or s is None or e == 0:
        return None
    return abs(e - s) / abs(e) * 100


def _target_distance_pct(entry: Any, tp: Any) -> float | None:
    """Take-profit distance as a percentage of entry price -- how
    ambitious the target is, independent of R:R."""
    e, t = _num(entry), _num(tp)
    if e is None or t is None or e == 0:
        return None
    return abs(t - e) / abs(e) * 100


def _distance_pct_similarity(a_pct: float | None, b_pct: float | None) -> float:
    if a_pct is None or b_pct is None or a_pct <= 0 or b_pct <= 0:
        return 0.0
    # Log space, like _lots_similarity -- these percentages can span
    # orders of magnitude (a tight 0.05% forex stop vs. a wide 3% crypto
    # stop), so comparing them on a linear scale would make everything
    # except near-identical values look maximally dissimilar.
    return _gaussian(math.log10(a_pct), math.log10(b_pct), 0.5)


def _entry_proximity(candidate: dict, entry: dict) -> float:
    if not _pair_equal(candidate.get("pair"), entry.get("pair")):
        return 0.0
    a, b = _num(candidate.get("entry")), _num(entry.get("entry"))
    if a is None or b is None or a == 0:
        return 0.0
    sigma = 0.005 * a
    if sigma == 0:
        return 0.0
    return math.exp(-((abs(a - b) / sigma) ** 2))


def _feature_similarity(feature: str, candidate: dict, entry: dict, candidate_tags: list[str], entry_tags: list[str]) -> float:
    if feature == "pair":
        return _pair_equal(candidate.get("pair"), entry.get("pair"))
    if feature == "direction":
        return _cat_equal(candidate.get("direction"), entry.get("direction"))
    if feature == "asset":
        return _cat_equal(candidate.get("asset"), entry.get("asset"))
    if feature == "session":
        return _cat_equal(candidate.get("session"), entry.get("session"))
    if feature == "h4Trend":
        return _cat_equal(candidate.get("h4Trend"), entry.get("h4Trend"))
    if feature == "h4PoiType":
        return _cat_equal(candidate.get("h4PoiType") or candidate.get("poi"), entry.get("h4PoiType") or entry.get("poi"))
    if feature == "premiumDiscount":
        return _cat_equal(candidate.get("premiumDiscount"), entry.get("premiumDiscount"))
    if feature == "bos":
        return _bool_presence("BOS", candidate_tags, entry_tags)
    if feature == "choch":
        return _bool_presence("CHOCH", candidate_tags, entry_tags)
    if feature == "liquiditySweep":
        return _bool_presence("Liquidity Sweep", candidate_tags, entry_tags)
    if feature == "fvg":
        return _bool_presence("FVG", candidate_tags, entry_tags)
    if feature == "news":
        return _news_similarity(candidate.get("news"), entry.get("news"))
    if feature == "rr":
        return _rr_similarity(candidate.get("rr"), entry.get("rr"))
    if feature == "confidence":
        return _confidence_similarity(candidate.get("confidence"), entry.get("confidence"))
    if feature == "lots":
        return _lots_similarity(candidate.get("lots"), entry.get("lots"))
    if feature == "entryProximity":
        return _entry_proximity(candidate, entry)
    if feature == "stopDistancePct":
        a = _stop_distance_pct(candidate.get("entry"), candidate.get("sl"))
        b = _stop_distance_pct(entry.get("entry"), entry.get("sl"))
        return _distance_pct_similarity(a, b)
    if feature == "targetDistancePct":
        a = _target_distance_pct(candidate.get("entry"), candidate.get("tp"))
        b = _target_distance_pct(entry.get("entry"), entry.get("tp"))
        return _distance_pct_similarity(a, b)
    if feature == "orderType":
        return _order_type_similarity(candidate.get("orderType"), entry.get("orderType"))
    return 0.0


def _feature_present(feature: str, candidate: dict, candidate_tags: list[str]) -> bool:
    if feature == "pair":
        return bool(candidate.get("pair"))
    if feature == "direction":
        return bool(candidate.get("direction"))
    if feature == "asset":
        return bool(candidate.get("asset"))
    if feature == "session":
        return bool(candidate.get("session"))
    if feature == "h4Trend":
        return bool(candidate.get("h4Trend"))
    if feature == "h4PoiType":
        return bool(candidate.get("h4PoiType") or candidate.get("poi"))
    if feature == "premiumDiscount":
        return bool(candidate.get("premiumDiscount"))
    if feature in ("bos", "choch", "liquiditySweep", "fvg"):
        tag = {"bos": "BOS", "choch": "CHOCH", "liquiditySweep": "Liquidity Sweep", "fvg": "FVG"}[feature]
        return tag in candidate_tags
    if feature == "news":
        return candidate.get("news") in _NEWS_RANK
    if feature == "rr":
        return _num(candidate.get("rr")) is not None
    if feature == "confidence":
        return _num(candidate.get("confidence")) is not None
    if feature == "lots":
        return _num(candidate.get("lots")) is not None
    if feature == "entryProximity":
        return bool(candidate.get("pair")) and _num(candidate.get("entry")) is not None
    if feature == "stopDistancePct":
        return _stop_distance_pct(candidate.get("entry"), candidate.get("sl")) is not None
    if feature == "targetDistancePct":
        return _target_distance_pct(candidate.get("entry"), candidate.get("tp")) is not None
    if feature == "orderType":
        return _order_type_category(candidate.get("orderType")) is not None
    return False


def _average(values: list[float]) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return sum(nums) / len(nums) if nums else None


def _score_of(entry: dict, key: str) -> float | None:
    if isinstance(entry.get(key), (int, float)) and not isinstance(entry.get(key), bool):
        return entry[key]
    ai = entry.get("ai")
    if isinstance(ai, dict) and isinstance(ai.get(key), (int, float)):
        return ai[key]
    return None


def _outcome(entry: dict) -> str:
    pnl = entry.get("pnl") or 0
    return "Win" if pnl > 0 else "Loss" if pnl < 0 else "Breakeven"


def search_similar(
    candidate: dict[str, Any] | None,
    history: list[dict[str, Any]] | None,
    *,
    weights: dict[str, float] | None = None,
    min_similarity: float = 50.0,
    limit: int | None = 10,
) -> dict:
    """search_similar(candidate, history, weights=None, min_similarity=50, limit=10)

    Weighted-v1 similarity (Section 7): every present candidate feature
    contributes ``w_f * S_f(candidate, entry)`` to the match score,
    normalized by the sum of present weights. Continuous features
    (RR, confidence, lots, entry proximity) are graded via Gaussian
    similarity rather than binary tolerance windows.
    """
    candidate = candidate or {}
    history = history or []
    active_weights = normalize_similarity_weights(weights)
    candidate_tags = _tags(candidate)

    present_features = [f for f in active_weights if _feature_present(f, candidate, candidate_tags)]
    present_weight = sum(active_weights[f] for f in present_features)

    scored = []
    for entry in history:
        if candidate.get("id") and entry.get("id") == candidate.get("id"):
            continue
        entry_tags = _tags(entry)
        contributions = []
        raw_score = 0.0
        for feature in present_features:
            sim = _feature_similarity(feature, candidate, entry, candidate_tags, entry_tags)
            weight = active_weights[feature]
            contribution = weight * sim
            raw_score += contribution
            contributions.append(
                {"feature": feature, "weight": round(weight, 4), "similarity": round(sim, 4), "contribution": round(contribution, 4)}
            )
        similarity = (100 * raw_score / present_weight) if present_weight > 0 else 0.0
        contributions.sort(key=lambda c: c["contribution"], reverse=True)
        scored.append({"entry": entry, "similarity": similarity, "contributions": contributions[:3]})

    scored = [s for s in scored if s["similarity"] >= min_similarity]
    scored.sort(key=lambda s: (s["similarity"], abs(s["entry"].get("pnl") or 0)), reverse=True)
    if limit is not None:
        scored = scored[: max(0, min(100, limit))]

    similar = [
        {
            **s["entry"],
            "similarity": round(s["similarity"], 2),
            "contributions": s["contributions"],
            "outcome": _outcome(s["entry"]),
        }
        for s in scored
    ]
    wins = len([e for e in similar if (e.get("pnl") or 0) > 0])
    losses = len([e for e in similar if (e.get("pnl") or 0) < 0])
    breakeven = len(similar) - wins - losses
    total_pnl = sum(float(e.get("pnl") or 0) for e in similar)

    mean_similarity = _average([e["similarity"] for e in similar]) or 0.0
    match_confidence = min(1.0, len(similar) / 5) * (mean_similarity / 100)

    return {
        "similar": similar,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "winRate": (wins / len(similar) * 100) if similar else None,
        "averageRR": _average([_num(e.get("rr")) for e in similar if _num(e.get("rr")) is not None]),
        "averageProfit": (total_pnl / len(similar)) if similar else None,
        "averageRuleScore": _average([s for s in (_score_of(e, "ruleScore") for e in similar) if s is not None]),
        "averageExecutionScore": _average([s for s in (_score_of(e, "executionScore") for e in similar) if s is not None]),
        "confidence": round(match_confidence, 4),
        "algorithm": "weighted-v1",
        "weightsSnapshot": active_weights,
    }


# --- Legacy binary-match algorithm (Sprint 5 parity / regression tests) ----


def _similar_confidence_legacy(a: Any, b: Any) -> bool:
    av, bv = _num(a), _num(b)
    if av is None or bv is None:
        return False
    if av <= 10:
        av *= 10
    if bv <= 10:
        bv *= 10
    return abs(av - bv) <= 15


def _similar_rr_legacy(a: Any, b: Any) -> bool:
    av, bv = _num(a), _num(b)
    if av is None or bv is None:
        return False
    return abs(av - bv) <= 0.5


def _legacy_score(candidate: dict, entry: dict) -> dict:
    score = 0.0
    possible = 0.0

    def add(key: str, known: bool, match: bool) -> None:
        nonlocal score, possible
        if not known:
            return
        possible += LEGACY_SIMILAR_TRADE_WEIGHTS[key]
        if match:
            score += LEGACY_SIMILAR_TRADE_WEIGHTS[key]

    candidate_tags = _tags(candidate)
    entry_tags = _tags(entry)
    add("pair", bool(candidate.get("pair")), bool(entry.get("pair")) and str(entry["pair"]).upper() == str(candidate.get("pair")).upper())
    add("direction", bool(candidate.get("direction")), entry.get("direction") == candidate.get("direction"))
    add("asset", bool(candidate.get("asset")), entry.get("asset") == candidate.get("asset"))
    add("session", bool(candidate.get("session")), entry.get("session") == candidate.get("session"))
    add("trend", bool(candidate.get("h4Trend")), entry.get("h4Trend") == candidate.get("h4Trend"))
    add(
        "poi",
        bool(candidate.get("h4PoiType") or candidate.get("poi")),
        (entry.get("h4PoiType") or entry.get("poi")) == (candidate.get("h4PoiType") or candidate.get("poi")),
    )
    add("bos", "BOS" in candidate_tags, "BOS" in entry_tags)
    add("choch", "CHOCH" in candidate_tags, "CHOCH" in entry_tags)
    add("liquiditySweep", "Liquidity Sweep" in candidate_tags, "Liquidity Sweep" in entry_tags)
    add("rr", candidate.get("rr") not in (None, ""), _similar_rr_legacy(candidate.get("rr"), entry.get("rr")))
    add(
        "confidence",
        candidate.get("confidence") not in (None, ""),
        _similar_confidence_legacy(candidate.get("confidence"), entry.get("confidence")),
    )

    percentage = round((score / possible) * 100) if possible > 0 else 0
    return {"score": score, "possible": possible, "percentage": percentage}


def search_similar_legacy(candidate: dict[str, Any] | None, history: list[dict[str, Any]] | None) -> dict:
    """search_similar_legacy(candidate, history) — Sprint 5's exact
    binary-match algorithm, kept for ``algorithm="legacy"`` regression
    comparisons per Section 6's engine mapping table."""
    candidate = candidate or {}
    history = history or []
    scored = [
        {"entry": e, **_legacy_score(candidate, e)}
        for e in history
        if not candidate.get("id") or e.get("id") != candidate.get("id")
    ]
    scored = [s for s in scored if s["percentage"] >= LEGACY_MIN_PERCENT]
    scored.sort(key=lambda s: (s["percentage"], abs(s["entry"].get("pnl") or 0)), reverse=True)

    similar = [{**s["entry"], "similarity": s["percentage"], "outcome": _outcome(s["entry"])} for s in scored]
    wins = len([e for e in similar if (e.get("pnl") or 0) > 0])
    losses = len([e for e in similar if (e.get("pnl") or 0) < 0])
    breakeven = len(similar) - wins - losses
    total_pnl = sum(float(e.get("pnl") or 0) for e in similar)

    mean_similarity = _average([e["similarity"] for e in similar]) or 0.0
    match_confidence = min(1.0, len(similar) / 5) * (mean_similarity / 100)

    return {
        "similar": similar,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "winRate": (wins / len(similar) * 100) if similar else None,
        "averageRR": _average([_num(e.get("rr")) for e in similar if _num(e.get("rr")) is not None]),
        "averageProfit": (total_pnl / len(similar)) if similar else None,
        "averageRuleScore": _average([s for s in (_score_of(e, "ruleScore") for e in similar) if s is not None]),
        "averageExecutionScore": _average([s for s in (_score_of(e, "executionScore") for e in similar) if s is not None]),
        "confidence": round(match_confidence, 4),
        "version": SIMILAR_TRADE_VERSION,
        "algorithm": "legacy",
        "weightsSnapshot": LEGACY_SIMILAR_TRADE_WEIGHTS,
    }
