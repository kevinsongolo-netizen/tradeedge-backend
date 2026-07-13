"""API tests for the Sprint 14 Live MT5 Feed (``/api/v1/live/*``).
Reuses the hand-verified bullish candle series from
``tests/chart/test_candle_smc_engine.py`` so the expected trend is
known ground truth, not a guess."""
from tests.chart.test_candle_smc_engine import _BULLISH_ROWS

_CANDLES_PAYLOAD = [
    {"time": str(i), "open": o, "high": h, "low": l, "close": c}
    for i, (o, h, l, c) in enumerate(_BULLISH_ROWS)
]


def test_latest_returns_404_before_any_ingest(client):
    resp = client.get("/api/v1/live/latest", params={"symbol": "EURUSD", "timeframe": "H4"})
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_ingest_then_latest_round_trip(client):
    ingest_resp = client.post(
        "/api/v1/live/ingest",
        json={"symbol": "EURUSD", "timeframe": "H4", "candles": _CANDLES_PAYLOAD, "plannedRr": 3.0},
    )
    assert ingest_resp.status_code == 200, ingest_resp.text
    ingest_body = ingest_resp.json()
    assert ingest_body["analysis"]["trend"] == "Bullish"

    latest_resp = client.get("/api/v1/live/latest", params={"symbol": "EURUSD", "timeframe": "H4"})
    assert latest_resp.status_code == 200, latest_resp.text
    latest_body = latest_resp.json()
    assert latest_body["symbol"] == "EURUSD"
    assert latest_body["timeframe"] == "H4"
    assert latest_body["analysis"]["trend"] == "Bullish"
    assert "updatedAt" in latest_body


def test_ingest_upserts_same_symbol_timeframe(client):
    client.post(
        "/api/v1/live/ingest",
        json={"symbol": "GBPUSD", "timeframe": "M15", "candles": _CANDLES_PAYLOAD},
    )
    client.post(
        "/api/v1/live/ingest",
        json={"symbol": "GBPUSD", "timeframe": "M15", "candles": _CANDLES_PAYLOAD},
    )
    resp = client.get("/api/v1/live/latest", params={"symbol": "GBPUSD", "timeframe": "M15"})
    assert resp.status_code == 200, resp.text


def test_different_symbols_are_independent(client):
    client.post(
        "/api/v1/live/ingest",
        json={"symbol": "BTCUSD", "timeframe": "H4", "candles": _CANDLES_PAYLOAD},
    )
    resp = client.get("/api/v1/live/latest", params={"symbol": "ETHUSD", "timeframe": "H4"})
    assert resp.status_code == 404, resp.text


def test_ingest_plain_format_for_mt5_ea(client):
    resp = client.post(
        "/api/v1/live/ingest?format=plain",
        json={"symbol": "EURUSD", "timeframe": "H4", "candles": _CANDLES_PAYLOAD, "plannedRr": 3.0},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/plain")
    text = resp.text
    assert "STATUS=" in text
    assert "RECOMMENDATION=" in text
    assert "HEADLINE=" in text
    assert "CONFIDENCE=" in text


def test_ingest_rejects_too_few_candles(client):
    resp = client.post(
        "/api/v1/live/ingest",
        json={"symbol": "EURUSD", "timeframe": "H4", "candles": _CANDLES_PAYLOAD[:3]},
    )
    assert resp.status_code == 422, resp.text
