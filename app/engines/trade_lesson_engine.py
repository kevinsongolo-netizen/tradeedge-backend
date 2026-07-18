"""Post-trade planned-vs-actual lesson engine (Sprint 20 Phase 2, item #4).

The Sprint 11 ``trade_review_engine`` answers "did I follow my own
checklist" (rules-followed/tags/exit-reason vs a fixed R:R minimum).
This engine answers a different question the user asked for
explicitly: "how does what I actually did on THIS trade compare to
what has worked for ME on setups like this before" -- planned entry/
stop/target vs how the trader's own similar past trades were sized and
how they turned out. It deliberately never invents an unverifiable
claim (e.g. "you entered too early" needs intrabar/MFE data this app
doesn't have) -- every lesson here is derived directly from numbers
already in the journal: stop distance %, target distance %, and the
win/loss mix of the trader's own similar setups (via the same weighted
``search_similar`` used by the pre-trade insight, so "similar" means
the same thing in both places).

Pure function, no I/O, no HTTP knowledge -- same convention as every
other ``app/engines/*.py`` module.
"""
from __future__ import annotations

from typing import Any

from app.engines.similar_engine import search_similar

TRADE_LESSON_VERSION = "1.0"

# Below this many similar closed trades, any "your winners tend to..."
# comparison would be drawing a pattern out of noise -- so we say so
# plainly instead of guessing.
MIN_SIMILAR_FOR_LESSON = 3

# A trade only counts as meaningfully tighter/wider (or a target only
# counts as meaningfully more/less ambitious) than the comparison group
# once it clears these ratios -- small differences aren't worth a
# lesson.
_TIGHT_STOP_RATIO = 0.7
_WIDE_STOP_RATIO = 1.5
_AMBITIOUS_TARGET_RATIO = 1.5
_CONSERVATIVE_TARGET_RATIO = 0.7


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stop_distance_pct(entry: Any, sl: Any) -> float | None:
    e, s = _num(entry), _num(sl)
    if e is None or s is None or e == 0:
        return None
    return abs(e - s) / abs(e) * 100


def _target_distance_pct(entry: Any, tp: Any) -> float | None:
    e, t = _num(entry), _num(tp)
    if e is None or t is None or e == 0:
        return None
    return abs(t - e) / abs(e) * 100


def _average(values: list[float | None]) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float))]
    return sum(nums) / len(nums) if nums else None


def _outcome_of(entry: dict[str, Any]) -> str | None:
    """Best-effort outcome for a history row: prefer an explicit
    ``outcome`` field (as ``search_similar`` attaches), else derive it
    from ``pnl``."""
    outcome = entry.get("outcome")
    if outcome:
        return outcome
    pnl = _num(entry.get("pnl"))
    if pnl is None:
        return None
    if pnl > 0:
        return "Win"
    if pnl < 0:
        return "Loss"
    return "Breakeven"


def build_trade_lesson(
    trade: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
    *,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """build_trade_lesson(trade, history, weights=None)

    ``trade``: the just-closed trade, in the same camelCase shape
    ``Trade.to_engine_dict()``/``to_candidate_dict()`` produce (must
    have ``exit`` set -- raises if not, same contract as
    ``build_trade_review``).
    ``history``: the trader's other trades in the same shape (this
    trade's own id, if present, is safely excluded by
    ``search_similar``'s existing id check -- no need to pre-filter).
    """
    history = history or []
    if trade.get("exit") is None:
        raise ValueError("This trade doesn't have an exit price yet -- close it before requesting a lesson.")

    pnl = _num(trade.get("pnl"))
    if pnl is not None and pnl > 0:
        outcome = "Win"
    elif pnl is not None and pnl < 0:
        outcome = "Loss"
    elif pnl == 0:
        outcome = "Breakeven"
    else:
        outcome = "Unknown"

    result = search_similar(trade, history, weights=weights, min_similarity=40.0, limit=20)
    similar = result["similar"]

    if len(similar) < MIN_SIMILAR_FOR_LESSON:
        return {
            "outcome": outcome,
            "hasEnoughHistory": False,
            "sampleSize": len(similar),
            "wins": 0,
            "losses": 0,
            "lessons": [
                "Not enough similar closed trades yet ({found} found, need at least {needed}) to compare this one "
                "against your own pattern -- the more you log, the sharper this gets.".format(
                    found=len(similar), needed=MIN_SIMILAR_FOR_LESSON
                )
            ],
            "patterns": [],
            "version": TRADE_LESSON_VERSION,
        }

    winners = [s for s in similar if _outcome_of(s) == "Win"]
    losers = [s for s in similar if _outcome_of(s) == "Loss"]

    this_stop_pct = _stop_distance_pct(trade.get("entry"), trade.get("sl"))
    this_target_pct = _target_distance_pct(trade.get("entry"), trade.get("tp"))
    winners_stop_pct = _average([_stop_distance_pct(w.get("entry"), w.get("sl")) for w in winners])
    winners_target_pct = _average([_target_distance_pct(w.get("entry"), w.get("tp")) for w in winners])

    lessons: list[str] = []

    if this_stop_pct is not None and winners_stop_pct is not None and len(winners) >= 2:
        if this_stop_pct < winners_stop_pct * _TIGHT_STOP_RATIO:
            lessons.append(
                "Your stop loss on this trade ({this:.2f}% from entry) was noticeably tighter than your average "
                "winning trade on similar setups ({avg:.2f}%) -- tight stops on this kind of setup have historically "
                "been more likely to get clipped before the move plays out for you.".format(
                    this=this_stop_pct, avg=winners_stop_pct
                )
            )
        elif this_stop_pct > winners_stop_pct * _WIDE_STOP_RATIO:
            lessons.append(
                "Your stop loss on this trade ({this:.2f}% from entry) was noticeably wider than your average "
                "winning trade on similar setups ({avg:.2f}%) -- worth checking whether a tighter, better-placed "
                "stop would still have given the trade room to work.".format(this=this_stop_pct, avg=winners_stop_pct)
            )

    if this_target_pct is not None and winners_target_pct is not None and len(winners) >= 2:
        if this_target_pct > winners_target_pct * _AMBITIOUS_TARGET_RATIO:
            lessons.append(
                "Your take profit ({this:.2f}% away) was noticeably more ambitious than what's typically worked on "
                "similar setups ({avg:.2f}%) -- your winners on this kind of setup tend to bank profit sooner.".format(
                    this=this_target_pct, avg=winners_target_pct
                )
            )
        elif this_target_pct < winners_target_pct * _CONSERVATIVE_TARGET_RATIO:
            lessons.append(
                "Your take profit ({this:.2f}% away) was noticeably more conservative than what's typically worked "
                "on similar setups ({avg:.2f}%) -- your winners on this kind of setup have tended to run further "
                "than this one was given room to.".format(this=this_target_pct, avg=winners_target_pct)
            )

    patterns: list[str] = []
    win_rate = (len(winners) / len(similar) * 100) if similar else None

    if outcome == "Loss" and win_rate is not None and win_rate >= 60:
        patterns.append(
            "Setups like this have actually worked out for you {rate:.0f}% of the time in your history ({w} of {n} "
            "similar trades) -- this looks like a good setup that just didn't play out this time, not a flawed "
            "one.".format(rate=win_rate, w=len(winners), n=len(similar))
        )
    if outcome == "Win" and win_rate is not None and (100 - win_rate) >= 40:
        patterns.append(
            "Worth noting: setups like this have also lost {rate:.0f}% of the time in your history ({l} of {n}) -- "
            "a good outcome this time, but size accordingly next time.".format(
                rate=100 - win_rate, l=len(losers), n=len(similar)
            )
        )
    if outcome == "Loss" and win_rate is not None and win_rate < 40 and len(losers) >= 2:
        patterns.append(
            "Setups like this have lost for you {rate:.0f}% of the time in your history ({l} of {n} similar trades) "
            "-- this looks less like bad luck on one trade and more like a setup that hasn't been working for "
            "you.".format(rate=100 - win_rate, l=len(losers), n=len(similar))
        )

    if not lessons:
        lessons.append(
            "No meaningful difference in stop or target sizing versus your own winning trades on similar setups -- "
            "your execution here was in line with what's worked before."
        )

    return {
        "outcome": outcome,
        "hasEnoughHistory": True,
        "sampleSize": len(similar),
        "wins": len(winners),
        "losses": len(losers),
        "lessons": lessons,
        "patterns": patterns,
        "version": TRADE_LESSON_VERSION,
    }
