"""Playbook Engine tests (Sprint 20 Phase 3 #6 -- "My Best Setups").

Confirms setups are ranked purely from the trader's own history (no
fixed "good setup" list), thin groups are excluded, best session/day
require their own minimum sample, example screenshots only ever come
from real winning trades' entry screenshots, and "average holding
time" is never fabricated (simply absent from the output)."""
from app.engines.playbook_engine import PLAYBOOK_MIN_SAMPLE, build_playbook


def _trade(poi, pnl, session, date, screenshots=None):
    return {
        "id": f"{poi}-{date}-{pnl}",
        "h4PoiType": poi,
        "pnl": pnl,
        "rr": 2.0 if pnl > 0 else 1.0,
        "session": session,
        "date": date,
        "screenshots": screenshots or [],
    }


def test_empty_history_returns_no_setups():
    result = build_playbook([])
    assert result["setups"] == []
    assert result["sampleSize"] == 0


def test_poi_type_below_minimum_sample_is_excluded():
    history = [_trade("Bullish OB", 10, "London", "2026-01-01")]
    result = build_playbook(history)
    assert result["setups"] == []


def test_poi_type_at_minimum_sample_is_included_and_ranked():
    history = [_trade("Bullish OB", 10, "London", f"2026-01-0{i}") for i in range(1, 1 + PLAYBOOK_MIN_SAMPLE)]
    result = build_playbook(history)
    assert len(result["setups"]) == 1
    setup = result["setups"][0]
    assert setup["poiType"] == "Bullish OB"
    assert setup["count"] == PLAYBOOK_MIN_SAMPLE
    assert setup["winRate"] == 100.0


def test_multiple_setups_are_ranked_best_first():
    strong = [_trade("Bullish OB", 50, "London", f"2026-01-0{i}") for i in range(1, 6)]
    weak = [_trade("Bearish FVG", -20, "Asian", f"2026-02-0{i}") for i in range(1, 6)]
    result = build_playbook(strong + weak)
    keys = [s["poiType"] for s in result["setups"]]
    assert keys[0] == "Bullish OB"
    assert keys[-1] == "Bearish FVG"


def test_best_session_requires_its_own_minimum_sample():
    # 5 London trades (real sample) all winners, plus a single New York
    # trade that also happens to win -- New York's 100% win rate from
    # one trade shouldn't beat London's real 5-trade sample.
    history = (
        [_trade("Bullish OB", 10, "London", f"2026-01-0{i}") for i in range(1, 6)]
        + [_trade("Bullish OB", 10, "New York", "2026-01-06")]
    )
    result = build_playbook(history)
    setup = result["setups"][0]
    assert setup["bestSession"] == "London"


def test_example_screenshots_only_from_winning_trades_with_entry_shots():
    history = [
        _trade("Bullish OB", 10, "London", "2026-01-01", [{"url": "https://x/win1.png", "kind": "entry"}]),
        _trade("Bullish OB", -10, "London", "2026-01-02", [{"url": "https://x/loss1.png", "kind": "entry"}]),
        _trade("Bullish OB", 10, "London", "2026-01-03", []),  # winner, no screenshot
        _trade("Bullish OB", 10, "London", "2026-01-04", [{"url": "https://x/win2.png", "kind": "exit"}]),  # wrong kind
    ]
    result = build_playbook(history)
    shots = result["setups"][0]["exampleScreenshots"]
    assert shots == ["https://x/win1.png"]


def test_example_screenshots_capped_and_most_recent_first():
    history = [
        _trade("Bullish OB", 10, "London", f"2026-01-0{i}", [{"url": f"https://x/{i}.png", "kind": "entry"}])
        for i in range(1, 6)
    ]
    result = build_playbook(history)
    shots = result["setups"][0]["exampleScreenshots"]
    assert len(shots) == 2
    assert shots[0] == "https://x/5.png"  # most recent date first


def test_output_never_includes_a_holding_time_field():
    # No entered_at/closed_at data exists yet (see module docstring) --
    # this must never be silently faked as e.g. 0 or null-that-looks-real.
    history = [_trade("Bullish OB", 10, "London", f"2026-01-0{i}") for i in range(1, 6)]
    result = build_playbook(history)
    setup = result["setups"][0]
    assert "averageHoldingTime" not in setup
    assert "holdingTime" not in setup
