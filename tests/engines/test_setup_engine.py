"""Setup Engine tests."""
from app.engines.setup_engine import analyze_setups, group_stats


def test_group_stats_ranks_by_win_rate_and_sample_size():
    entries = [
        {"pair": "EURUSD", "pnl": 100},
        {"pair": "EURUSD", "pnl": 100},
        {"pair": "EURUSD", "pnl": 100},
        {"pair": "GBPUSD", "pnl": 100},
    ]
    groups = group_stats(entries, lambda e: e["pair"])
    assert groups[0]["key"] == "EURUSD"  # more samples at 100% WR ranks first
    assert groups[0]["confident"] is True
    assert groups[1]["confident"] is False


def test_analyze_setups_finds_best_setup_string():
    entries = [
        {"pair": "eurusd", "session": "London", "h4PoiType": "OB", "m15Confirmations": ["BOS"], "pnl": 50, "date": "2026-01-01"}
        for _ in range(3)
    ]
    result = analyze_setups(entries)
    assert result["bestSetup"] is not None
    assert "EURUSD" in result["bestSetup"]
    assert result["sampleSize"] == 3


def test_empty_entries_return_empty_dimensions():
    result = analyze_setups([])
    assert result["sampleSize"] == 0
    assert result["bestSetup"] is None
