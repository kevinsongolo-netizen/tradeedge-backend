"""API tests for ``POST /api/v1/backtest/run`` (Sprint 13)."""
from tests.chart.test_candle_smc_engine import _BULLISH_ROWS


def test_backtest_run_too_few_candles_is_validation_error(client):
    candles = [
        {"time": str(i), "open": o, "high": h, "low": l, "close": c}
        for i, (o, h, l, c) in enumerate(_BULLISH_ROWS[:3])
    ]
    resp = client.post("/api/v1/backtest/run", json={"candles": candles})
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_backtest_run_end_to_end_no_crash(client):
    # Repeats the hand-verified bullish series a few times to get past
    # MIN_TOTAL_CANDLES — this is a real end-to-end wiring check (no
    # mocking), so it just needs to return a coherent result, not
    # necessarily any trades.
    rows = _BULLISH_ROWS * 4
    candles = [
        {"time": str(i), "open": o, "high": h, "low": l, "close": c}
        for i, (o, h, l, c) in enumerate(rows)
    ]
    resp = client.post("/api/v1/backtest/run", json={"candles": candles, "lookbackWindow": 20})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "totalTrades" in body
    assert "winRate" in body
    assert isinstance(body["trades"], list)
