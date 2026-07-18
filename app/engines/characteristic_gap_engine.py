"""Characteristic Gap Engine (Sprint 20 Phase 4, extended Phase 5).

Answers three of the trader's own questions, directly from their own
history -- never a verdict:

  - "What characteristics do my winning trades have that this one
    does not?"
  - "What characteristics do my losing trades have that this one
    also has?"
  - "How many of my winning trades' typical characteristics does this
    setup actually match?" (Sprint 20 Phase 5 -- "This setup only
    matches 2 of those 5 characteristics.")

Takes the SAME ``similar`` list ``setup_insight_engine.build_setup_
insight`` already computed (via ``similar_engine.search_similar``) --
each entry there is the trader's own logged trade (full
``Trade.to_engine_dict()`` shape) plus its similarity score, so no
extra history fetch or translation is needed here.

Splits that list into its winning and losing subsets and looks for a
DOMINANT value on categorical/tag dimensions (POI type, premium/
discount zone, session, trend, BOS/CHoCH/liquidity-sweep/FVG presence)
plus a TYPICAL value on two continuous ones (stop size, R:R -- Sprint
20 Phase 5, per the trader's own "smaller stop loss / higher R:R"
example). "Dominant"/"typical" means at least ``DOMINANT_SHARE`` of
that subset shares the same categorical value (or, for the continuous
pair, the group's average) -- a single outlier trade never gets to
speak for "your winners" or "your losers". Below ``MIN_SAMPLE_FOR_GAP``
winners (or losers), that side is skipped entirely rather than drawing
a pattern from 1-2 trades -- same honesty bar as the rest of Sprint 20
Phase 4 (see ``setup_insight_engine.MIN_SIMILAR_FOR_CONFIDENT_STAT`` and
``trade_lesson_engine.MIN_SIMILAR_FOR_LESSON``, both also 3).

Pure function, no I/O -- same convention as every other engine here.
"""
from __future__ import annotations

from typing import Any

MIN_SAMPLE_FOR_GAP = 3
DOMINANT_SHARE = 0.6
# Sprint 20 Phase 7 -- cap on the ranked "why might this setup lose"
# weakness list, same instinct as _MAX_REASONS elsewhere: a short,
# readable list beats a wall of every gap/echo found.
MAX_WEAKNESSES = 8
# Sprint 20 Phase 9 ("Confidence-Tiered Reasoning") -- below this, a
# standalone weakness derived from a vision model's OWN judgment call
# (order block freshness, rejection strength, FVG mitigation -- as
# opposed to a directly-observed fact) gets hedged as a "Possible
# concern (NN% confidence)" instead of stated as settled fact, per the
# trader's own review of a live screenshot: these three specifically
# require inferring things a single static frame often can't fully
# prove, so asserting them with the same flat certainty as the pair or
# entry price overstates what the AI actually knows. Below this bar,
# severity is also downgraded from the standalone-flag default of 100
# to the confidence value itself, so a shaky, low-confidence concern
# naturally ranks below the historical winner/loser echoes it's mixed
# in with, rather than always winning "why this could lose" purely by
# being a standalone flag.
HIGH_CONFIDENCE_THRESHOLD = 70.0

# Categorical fields worth comparing directly (candidate vs. the
# dominant value in the winning/losing subset).
_CATEGORICAL_DIMENSIONS: list[tuple[str, str]] = [
    ("h4PoiType", "point-of-interest type"),
    ("premiumDiscount", "zone"),
    ("session", "session"),
    ("h4Trend", "trend"),
    # Sprint 20 Phase 6 -- the trader's own example of this comparison
    # explicitly listed "Same Pair"/"Same Session" alongside the
    # structural dimensions, so pair/direction join the winner-profile
    # comparison here too (they were previously only compared inside
    # similar_engine's search itself, never surfaced as their own
    # winner-profile checklist rows).
    ("pair", "pair"),
    ("direction", "direction"),
]

# Short checklist labels (Sprint 20 Phase 6) -- (matched label, missing
# label template). Missing uses the dominant WINNING value itself as
# the tag name (e.g. "London Session", "Bearish Order Block") rather
# than a generic "Different X", since that is what actually teaches the
# trader something ("your winners are usually London session -- this
# one is Asian").
_CATEGORICAL_CHECKLIST_LABELS: dict[str, tuple[str, str]] = {
    "h4PoiType": ("Same Order Block / POI Type", "{value}"),
    "premiumDiscount": ("Same Zone", "{value} Zone"),
    "session": ("Same Session", "{value} Session"),
    "h4Trend": ("Same Trend", "{value} Trend"),
    "pair": ("Same Pair", "{value}"),
    "direction": ("Same Direction", "{value}"),
}

# Tag-style dimensions use the SAME display name whether matched or
# missing (e.g. "✓ Liquidity Sweep" / "✗ Liquidity Sweep") -- the tag
# itself IS the characteristic being checked for.
_TAG_CHECKLIST_LABELS: dict[str, str] = {
    "BOS": "Break of Structure",
    "CHOCH": "Change of Character",
    "Liquidity Sweep": "Liquidity Sweep",
    "FVG": "Fair Value Gap",
    "Fresh Order Block": "First Touch Order Block",
    "Strong Rejection": "Strong Rejection Candle",
    "Large FVG": "Large Fair Value Gap",
}

# Structural tags (BOS/CHoCH/liquidity sweep/FVG) live inside
# m15Confirmations as a list of strings on both a candidate and a
# logged trade -- treated as present/absent rather than a single value.
_TAG_DIMENSIONS: list[tuple[str, str]] = [
    ("BOS", "a break of structure"),
    ("CHOCH", "a change of character"),
    ("Liquidity Sweep", "a liquidity sweep"),
    ("FVG", "an FVG"),
    # Sprint 20 Phase 6 -- the trader's own worked examples ("First
    # Touch Order Block", "Strong Rejection Candle", "Large Fair Value
    # Gap") named these specifically as things to compare winners
    # against, alongside the existing structural tags above.
    ("Fresh Order Block", "a fresh, untested Order Block"),
    ("Strong Rejection", "a strong rejection candle"),
    ("Large FVG", "a large Fair Value Gap"),
]

# Sprint 20 Phase 5 -- continuous dimensions (stop size, R:R). A single
# average stands in for "typical" here (there's no dominant value for a
# number the way there is for a category), and a candidate is only
# called "notably different" from it once the ratio clears a real gap
# -- not just any tiny numeric difference. Same ratio convention as
# app/engines/trade_lesson_engine.py's tight/wide-stop checks, kept as
# its own copy here per this app's per-engine self-containment
# convention.
_NOTABLY_LOWER_RATIO = 0.7   # candidate's value is this much (or less) of the group average
_NOTABLY_HIGHER_RATIO = 1.5  # candidate's value is this much (or more) of the group average


def _stop_distance_pct(trade: dict[str, Any]) -> float | None:
    entry, sl = trade.get("entry"), trade.get("sl")
    if not isinstance(entry, (int, float)) or not isinstance(sl, (int, float)) or entry == 0:
        return None
    return abs(entry - sl) / abs(entry) * 100


def _rr_value(trade: dict[str, Any]) -> float | None:
    rr = trade.get("rr")
    return float(rr) if isinstance(rr, (int, float)) else None


# (dimension key, human label, "lower means" phrase, "higher means" phrase, extractor)
_CONTINUOUS_DIMENSIONS: list[tuple[str, str, str, str, Any]] = [
    ("stopDistancePct", "stop loss size", "tighter", "wider", _stop_distance_pct),
    ("rr", "risk:reward", "lower", "higher", _rr_value),
]

# Checklist labels for the continuous dimensions above -- (matched
# label, missing label). Missing names whichever direction the
# candidate actually needs to move in (e.g. "Higher Risk:Reward"),
# mirroring the trader's own example phrasing ("Smaller stop loss,
# Higher R:R").
_CONTINUOUS_CHECKLIST_LABELS: dict[str, tuple[str, str]] = {
    "stopDistancePct": ("Similar Stop Size", "{word} Stop Loss"),
    "rr": ("Similar Risk:Reward", "{word} Risk:Reward"),
}


def _dominant_value(trades: list[dict[str, Any]], field: str) -> tuple[Any, float]:
    """Most common non-null value of ``field`` across ``trades`` and
    the share of (non-null-valued) trades that share it. ``(None, 0.0)``
    when nothing usable is present."""
    counts: dict[Any, int] = {}
    total = 0
    for t in trades:
        v = t.get(field)
        if v is None or v == "":
            continue
        counts[v] = counts.get(v, 0) + 1
        total += 1
    if not counts:
        return None, 0.0
    value, count = max(counts.items(), key=lambda kv: kv[1])
    return value, count / total


def _tag_presence_share(trades: list[dict[str, Any]], tag: str) -> float:
    if not trades:
        return 0.0
    present = sum(1 for t in trades if tag in (t.get("m15Confirmations") or []))
    return present / len(trades)


def _candidate_has_tag(candidate: dict[str, Any], tag: str) -> bool:
    return tag in (candidate.get("m15Confirmations") or [])


def _continuous_average(trades: list[dict[str, Any]], extractor: Any) -> float | None:
    values = [v for v in (extractor(t) for t in trades) if v is not None]
    return sum(values) / len(values) if values else None


def _evaluate_winner_profile(candidate: dict[str, Any], winners: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per dimension that was actually evaluable against the
    winning subset (dominant categorical value found, tag had a real
    majority presence, or a continuous average could be computed) --
    each ``{"matched": bool, "gapText": str | None}``. Used for BOTH
    the winner_gaps text list and the "matches N of M" score, so the
    two never drift out of sync with each other."""
    rows: list[dict[str, Any]] = []

    for field, label in _CATEGORICAL_DIMENSIONS:
        value, share = _dominant_value(winners, field)
        if value is None or share < DOMINANT_SHARE:
            continue
        matched = candidate.get(field) == value
        gap_text = None
        if not matched:
            gap_text = (
                f"Your winning trades on setups like this are usually in the {value} {label} "
                f"({share * 100:.0f}% of {len(winners)} similar wins) -- this one is "
                f"{candidate.get(field) or 'not set'}."
            )
        matched_label, missing_template = _CATEGORICAL_CHECKLIST_LABELS.get(field, (f"Same {label}", "{value}"))
        checklist_label = matched_label if matched else missing_template.format(value=value)
        rows.append({"matched": matched, "gapText": gap_text, "checklistLabel": checklist_label, "severity": share * 100})

    for tag, label in _TAG_DIMENSIONS:
        share = _tag_presence_share(winners, tag)
        if share < DOMINANT_SHARE:
            continue
        matched = _candidate_has_tag(candidate, tag)
        gap_text = None
        if not matched:
            gap_text = f"{share * 100:.0f}% of your similar winning trades had {label} -- this one doesn't."
        checklist_label = _TAG_CHECKLIST_LABELS.get(tag, tag)
        rows.append({"matched": matched, "gapText": gap_text, "checklistLabel": checklist_label, "severity": share * 100})

    for field, label, lower_word, higher_word, extractor in _CONTINUOUS_DIMENSIONS:
        avg = _continuous_average(winners, extractor)
        candidate_value = extractor(candidate)
        if avg is None or avg == 0 or candidate_value is None:
            continue
        ratio = candidate_value / avg
        matched = _NOTABLY_LOWER_RATIO <= ratio <= _NOTABLY_HIGHER_RATIO
        gap_text = None
        direction = higher_word if ratio < _NOTABLY_LOWER_RATIO else lower_word
        if not matched:
            gap_text = (
                f"Your winning trades usually have a {direction} {label} (avg {avg:.2f}) "
                f"than this one ({candidate_value:.2f})."
            )
        matched_label, missing_template = _CONTINUOUS_CHECKLIST_LABELS.get(
            field, (f"Similar {label}", "{word} " + label.title())
        )
        checklist_label = matched_label if matched else missing_template.format(word=direction.capitalize())
        # Severity for a continuous miss is how far the ratio strayed
        # from 1.0 (a perfect match), scaled to a comparable 0-100
        # range as the categorical/tag shares above.
        severity = min(100.0, abs(ratio - 1.0) * 100)
        rows.append({"matched": matched, "gapText": gap_text, "checklistLabel": checklist_label, "severity": severity})

    return rows


# Sprint 20 Phase 7 -- "AI Trade Mentor": characteristics with an
# unambiguous better/worse direction, used for the "what makes this
# setup better than my losers" comparison. Deliberately NOT extended to
# purely categorical dimensions with no inherent direction (session,
# pair, POI type, zone) -- claiming a session or pair is "better" than
# another would be fabricating a value judgment this app has no basis
# for; see similar_engine.py's module docstring for the same instinct
# applied elsewhere (documented gaps rather than invented certainty).
_GOOD_BAD_TAG_PAIRS: list[tuple[str, str, str]] = [
    ("Fresh Order Block", "Mitigated Order Block", "Fresh Order Block"),
    ("Strong Rejection", "Weak Rejection", "Strong Rejection Candle"),
    ("Large FVG", "Filled FVG", "Large Fair Value Gap"),
]

# Standalone weakness flags (Sprint 20 Phase 7) -- evaluated on the
# candidate ALONE, no trade history required, since each is
# self-evidently a weaker setup characteristic regardless of sample
# size (same instinct as chart/vision_provider.py's
# numberConsistencyWarning: a descriptive flag, never a verdict on
# whether to take the trade). "Counter-trend setup" reuses the EXACT
# SAME condition app/engines/mistake_engine.py's "counterTrend" mistake
# category already uses, for consistency across the app.
def _hedge_weakness(candidate: dict[str, Any], confidence_field: str, confident_label: str, hedged_label: str) -> dict[str, Any]:
    """Sprint 20 Phase 9 -- one standalone weakness row, worded
    according to how confident the vision model actually was in the
    judgment call behind it (see HIGH_CONFIDENCE_THRESHOLD's
    docstring). ``confidence_field`` is missing/None whenever the
    candidate wasn't built from a screenshot read that supplied one
    (an older read, or a manually-entered candidate) -- treated the
    same as a confident read (severity 100, unhedged label) rather
    than silently dropping the flag altogether, since "unknown
    confidence" isn't evidence the concern is wrong, just that this
    particular read didn't carry a confidence number."""
    confidence = candidate.get(confidence_field)
    if confidence is None or confidence >= HIGH_CONFIDENCE_THRESHOLD:
        return {"label": confident_label, "severity": 100.0}
    return {
        "label": f"Possible concern ({round(confidence)}% confidence): {hedged_label}",
        "severity": float(confidence),
    }


def _standalone_weaknesses(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    tags = candidate.get("m15Confirmations") or []
    weaknesses: list[dict[str, Any]] = []
    if "Mitigated Order Block" in tags:
        weaknesses.append(_hedge_weakness(
            candidate, "orderBlockFreshnessConfidence",
            "Order Block already mitigated",
            "This Order Block may have already been revisited/mitigated -- verify before relying on it.",
        ))
    if "Weak Rejection" in tags:
        weaknesses.append(_hedge_weakness(
            candidate, "rejectionStrengthConfidence",
            "Weak rejection candle",
            "A strong rejection candle hasn't been clearly confirmed yet.",
        ))
    if "Filled FVG" in tags:
        weaknesses.append(_hedge_weakness(
            candidate, "fvgMitigationConfidence",
            "Fair Value Gap already filled",
            "This Fair Value Gap may already be filled -- verify before relying on it.",
        ))
    # Counter-trend is a directly-derivable logical fact from two
    # already-stated categorical fields (trend label, order direction),
    # not a single-frame judgment call -- no hedging needed here.
    h4_trend = candidate.get("h4Trend")
    direction = candidate.get("direction")
    if (h4_trend == "Bullish" and direction == "sell") or (h4_trend == "Bearish" and direction == "buy"):
        weaknesses.append({"label": "Counter-trend setup", "severity": 100.0})
    return weaknesses


def _evaluate_loser_echo_profile(candidate: dict[str, Any], losers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mirror of ``_evaluate_winner_profile``, but against the LOSING
    subset: one row per evaluable dimension where the candidate ECHOES
    (shares) whatever losers on setups like this typically look like.
    Used both for the existing ``loserEchoes`` prose list and (Sprint
    20 Phase 7) the ranked weaknesses list -- an echoed loser
    characteristic is exactly what "why might this setup lose" means."""
    rows: list[dict[str, Any]] = []

    for field, label in _CATEGORICAL_DIMENSIONS:
        value, share = _dominant_value(losers, field)
        if value is None or share < DOMINANT_SHARE or candidate.get(field) != value:
            continue
        rows.append({
            "label": _CATEGORICAL_CHECKLIST_LABELS.get(field, (None, "{value}"))[1].format(value=value),
            "gapText": (
                f"Your losing trades on setups like this are usually in the {value} {label} "
                f"({share * 100:.0f}% of {len(losers)} similar losses) -- this one is too."
            ),
            "severity": share * 100,
        })

    for tag, label in _TAG_DIMENSIONS:
        share = _tag_presence_share(losers, tag)
        if share < DOMINANT_SHARE or not _candidate_has_tag(candidate, tag):
            continue
        rows.append({
            "label": _TAG_CHECKLIST_LABELS.get(tag, tag),
            "gapText": f"{share * 100:.0f}% of your similar losing trades also had {label} -- this one does too.",
            "severity": share * 100,
        })

    return rows


def _evaluate_better_than_losers(candidate: dict[str, Any], losers: list[dict[str, Any]]) -> list[str]:
    """"What makes this setup better than my losers?" (Sprint 20 Phase
    7) -- only ever claims "better" on a dimension with an unambiguous
    direction (see ``_GOOD_BAD_TAG_PAIRS`` and R:R below), and only once
    losers dominantly show the WORSE side of that dimension."""
    candidate_tags = candidate.get("m15Confirmations") or []
    reasons: list[str] = []

    for good_tag, bad_tag, label in _GOOD_BAD_TAG_PAIRS:
        bad_share = _tag_presence_share(losers, bad_tag)
        if bad_share >= DOMINANT_SHARE and good_tag in candidate_tags:
            reasons.append(f"{label} ({bad_share * 100:.0f}% of your similar losses had a {bad_tag.lower()} instead).")

    losers_avg_rr = _continuous_average(losers, _rr_value)
    candidate_rr = _rr_value(candidate)
    if losers_avg_rr and losers_avg_rr > 0 and candidate_rr is not None:
        ratio = candidate_rr / losers_avg_rr
        if ratio >= _NOTABLY_HIGHER_RATIO:
            reasons.append(f"Better Risk:Reward ({candidate_rr:.2f} vs. an average {losers_avg_rr:.2f} on your similar losses).")

    return reasons


def build_characteristic_gaps(
    candidate: dict[str, Any],
    similar: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Returns ``{hasEnoughData, winningTradeCount, losingTradeCount,
    winnerGaps, loserEchoes, winnerMatchCount, winnerMatchTotal,
    winnerMatchSummary}``.

    ``winnerGaps`` -- characteristics this trader's similar WINNING
    trades typically have that this candidate does NOT (now covering
    stop size and R:R too, not just categorical/tag dimensions).
    ``loserEchoes`` -- characteristics this trader's similar LOSING
    trades typically have (or typically lack) that this candidate ALSO
    has (or also lacks).
    ``winnerMatchCount``/``winnerMatchTotal`` -- e.g. 2 of 5 -- how many
    of the evaluable winning-profile dimensions this candidate actually
    matches; ``winnerMatchSummary`` is the same thing as one sentence,
    e.g. "This setup matches 2 of 5 characteristics your winning trades
    typically have." None/0 when there weren't enough winners to build
    a profile from at all.

    Purely descriptive, never a recommendation -- the trader decides
    what, if anything, to do about a gap."""
    similar = similar or []
    winners = [s for s in similar if s.get("outcome") == "Win"]
    losers = [s for s in similar if s.get("outcome") == "Loss"]

    winner_gaps: list[str] = []
    loser_echoes: list[str] = []
    winner_match_count = 0
    winner_match_total = 0
    winner_match_summary: str | None = None
    # Sprint 20 Phase 6 -- "Compared with your winning trades" checklist:
    # every evaluable dimension as a short ✓/✗ label (not just the
    # unmatched ones as prose sentences, which winnerGaps already gives).
    # ``matched`` rows render under a checkmark list, unmatched ones
    # under a "Missing:" heading -- see the trader's own worked example.
    winner_checklist: list[dict[str, Any]] = []

    # Sprint 20 Phase 7 -- "AI Trade Mentor": ranked weakness list
    # ("why might this setup lose") -- standalone flags always
    # evaluated, plus historical signals gated the same
    # MIN_SAMPLE_FOR_GAP honesty bar as everything else here.
    weaknesses: list[dict[str, Any]] = list(_standalone_weaknesses(candidate))
    better_than_losers: list[str] = []

    if len(winners) >= MIN_SAMPLE_FOR_GAP:
        profile = _evaluate_winner_profile(candidate, winners)
        winner_gaps = [row["gapText"] for row in profile if row["gapText"]]
        winner_checklist = [{"label": row["checklistLabel"], "matched": row["matched"]} for row in profile]
        winner_match_total = len(profile)
        winner_match_count = sum(1 for row in profile if row["matched"])
        if winner_match_total > 0:
            winner_match_summary = (
                f"This setup matches {winner_match_count} of {winner_match_total} characteristics "
                "your winning trades typically have."
            )
        weaknesses.extend(
            {"label": row["checklistLabel"], "severity": row["severity"]}
            for row in profile
            if not row["matched"]
        )

    if len(losers) >= MIN_SAMPLE_FOR_GAP:
        for field, label in _CATEGORICAL_DIMENSIONS:
            value, share = _dominant_value(losers, field)
            if value is not None and share >= DOMINANT_SHARE and candidate.get(field) == value:
                loser_echoes.append(
                    f"Your losing trades on setups like this are usually in the {value} {label} "
                    f"({share * 100:.0f}% of {len(losers)} similar losses) -- this one is too."
                )
        for tag, label in _TAG_DIMENSIONS:
            absent_share = 1.0 - _tag_presence_share(losers, tag)
            if absent_share >= DOMINANT_SHARE and not _candidate_has_tag(candidate, tag):
                loser_echoes.append(
                    f"{absent_share * 100:.0f}% of your similar losing trades were missing {label} "
                    "-- this one is missing it too."
                )
        for field, label, lower_word, higher_word, extractor in _CONTINUOUS_DIMENSIONS:
            avg = _continuous_average(losers, extractor)
            candidate_value = extractor(candidate)
            if avg is None or avg == 0 or candidate_value is None:
                continue
            ratio = candidate_value / avg
            # "Notably similar" is a narrower band than "notably
            # different" above -- being an echo of a losing pattern
            # should mean genuinely close, not just "not wildly off".
            if 0.85 <= ratio <= 1.15:
                loser_echoes.append(
                    f"Your losing trades on setups like this usually have a {label} around {avg:.2f} "
                    f"-- this one is {candidate_value:.2f}, very similar."
                )
        # Presence-based loser echoes (a bad tag this candidate has that
        # losers also typically have) feed the ranked weaknesses list --
        # a distinct, additive signal from the absence-echo prose above.
        weaknesses.extend(_evaluate_loser_echo_profile(candidate, losers))
        better_than_losers = _evaluate_better_than_losers(candidate, losers)

    # Dedupe by label (a standalone flag and a historical echo can name
    # the same characteristic -- e.g. "Order Block already mitigated"
    # is always flagged standalone, so a redundant historical echo of
    # the same tag is dropped rather than shown twice), then rank by
    # severity so the most likely reasons come first.
    seen_labels: set[str] = set()
    ranked_weaknesses: list[dict[str, Any]] = []
    for w in sorted(weaknesses, key=lambda w: w["severity"], reverse=True):
        if w["label"] in seen_labels:
            continue
        seen_labels.add(w["label"])
        ranked_weaknesses.append(w)
    ranked_weaknesses = ranked_weaknesses[:MAX_WEAKNESSES]

    return {
        "hasEnoughData": len(winners) >= MIN_SAMPLE_FOR_GAP or len(losers) >= MIN_SAMPLE_FOR_GAP,
        "winningTradeCount": len(winners),
        "losingTradeCount": len(losers),
        "winnerGaps": winner_gaps,
        "loserEchoes": loser_echoes,
        "winnerMatchCount": winner_match_count,
        "winnerMatchTotal": winner_match_total,
        "winnerMatchSummary": winner_match_summary,
        "winnerChecklist": winner_checklist,
        "weaknesses": ranked_weaknesses,
        "betterThanLosers": better_than_losers,
        # Sprint 20 Phase 7 -- "Improvement Suggestions": directly
        # derived from winner_checklist's own missing rows (never a
        # second, possibly-inconsistent computation) -- purely
        # descriptive ("this is what's usually present when you win"),
        # never a go/no-go verdict on the current setup.
        "improvementSuggestions": [f"Wait for: {row['label']}" for row in winner_checklist if not row["matched"]],
    }
