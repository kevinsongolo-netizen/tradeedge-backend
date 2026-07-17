"""API tests for the Live MT5 Feed (``/api/v1/live/*``).

Sprint 20 -- simplified to price-only ingest (no more rule engine on
every push, see app/_legacy/) plus the repurposed Scanner
(``/live/open-trade-alerts``): live price vs. the trader's own logged
open trades' SL/TP, never a verdict.
"""


def test_latest_returns_404_before_any_ingest(client):
    resp = client.get("/api/v1/live/latest", params={"symbol": "EURUSD", "timeframe": "H4"})
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_ingest_then_latest_round_trip(client):
    ingest_resp = client.post(
        "/api/v1/live/ingest",
        json={"symbol": "EURUSD", "timeframe": "H4", "price": 1.085, "bid": 1.0849, "ask": 1.0851},
    )
    assert ingest_resp.status_code == 200, ingest_resp.text
    assert ingest_resp.json()["price"] == 1.085

    latest_resp = client.get("/api/v1/live/latest", params={"symbol": "EURUSD", "timeframe": "H4"})
    assert latest_resp.status_code == 200, latest_resp.text
    latest_body = latest_resp.json()
    assert latest_body["symbol"] == "EURUSD"
    assert latest_body["timeframe"] == "H4"
    assert latest_body["price"] == 1.085
    assert latest_body["bid"] == 1.0849
    assert "updatedAt" in latest_body


def test_ingest_upserts_same_symbol_timeframe(client):
    client.post("/api/v1/live/ingest", json={"symbol": "GBPUSD", "timeframe": "M15", "price": 1.27})
    client.post("/api/v1/live/ingest", json={"symbol": "GBPUSD", "timeframe": "M15", "price": 1.28})
    resp = client.get("/api/v1/live/latest", params={"symbol": "GBPUSD", "timeframe": "M15"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["price"] == 1.28


def test_different_symbols_are_independent(client):
    client.post("/api/v1/live/ingest", json={"symbol": "BTCUSD", "timeframe": "H4", "price": 60000})
    resp = client.get("/api/v1/live/latest", params={"symbol": "ETHUSD", "timeframe": "H4"})
    assert resp.status_code == 404, resp.text


def test_ingest_plain_format_for_mt5_ea(client):
    resp = client.post(
        "/api/v1/live/ingest?format=plain",
        json={"symbol": "EURUSD", "timeframe": "H4", "price": 1.085},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/plain")
    text = resp.text
    assert "SYMBOL=EURUSD" in text
    assert "PRICE=1.085" in text


def test_open_trade_alerts_empty_with_no_open_trades(client):
    resp = client.get("/api/v1/live/open-trade-alerts")
    assert resp.status_code == 200, resp.text
    assert resp.json()["alerts"] == []


def test_open_trade_alerts_flags_sl_hit_for_logged_open_trade(client):
    client.post(
        "/api/v1/trades",
        json={
            "id": "open-1", "pair": "GOLDmicro", "direction": "buy", "asset": "Metals",
            "entry": 2400.0, "sl": 2390.0, "tp": 2420.0,
            # No "exit" -- this is an open trade, not yet closed.
        },
    )
    client.post("/api/v1/live/ingest", json={"symbol": "GOLDmicro", "timeframe": "M15", "price": 2389.0})

    resp = client.get("/api/v1/live/open-trade-alerts")
    assert resp.status_code == 200, resp.text
    alerts = resp.json()["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["tradeId"] == "open-1"
    assert alerts[0]["status"] == "SL_HIT"
    assert "tradeStatus" not in resp.text and "recommendation" not in resp.text


def test_open_trade_alerts_ignores_closed_trades(client):
    client.post(
        "/api/v1/trades",
        json={
            "id": "closed-1", "pair": "GOLDmicro", "direction": "buy", "asset": "Metals",
            "entry": 2400.0, "exit": 2420.0, "sl": 2390.0, "tp": 2420.0, "pnl": 200.0,
        },
    )
    client.post("/api/v1/live/ingest", json={"symbol": "GOLDmicro", "timeframe": "M15", "price": 2389.0})
    resp = client.get("/api/v1/live/open-trade-alerts")
    assert resp.json()["alerts"] == []
