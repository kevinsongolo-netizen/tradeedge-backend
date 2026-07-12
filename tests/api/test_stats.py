"""Statistics/health/setup/mistake API tests — ``/api/v1/stats/*`` (Section 4.5)."""

TRADES = [
    {"id": "w1", "date": "2026-01-01", "pair": "EURUSD", "direction": "buy", "asset": "Forex",
     "entry": 1.08, "exit": 1.09, "pnl": 60.0, "rr": 2.0, "session": "London"},
    {"id": "l1", "date": "2026-01-02", "pair": "EURUSD", "direction": "sell", "asset": "Forex",
     "entry": 1.09, "exit": 1.10, "pnl": -30.0, "rr": 1.0, "session": "London"},
    {"id": "w2", "date": "2026-01-03", "pair": "GBPUSD", "direction": "buy", "asset": "Forex",
     "entry": 1.25, "exit": 1.26, "pnl": 80.0, "rr": 2.5, "session": "New York"},
]


def _seed(client):
    for t in TRADES:
        client.post("/api/v1/trades", json=t)


def test_stats_summary(client):
    _seed(client)
    resp = client.get("/api/v1/stats/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalTrades"] == 3
    assert body["wins"] == 2
    assert body["losses"] == 1
    assert "byPair" in body and "EURUSD" in body["byPair"]


def test_stats_summary_filters_by_pair(client):
    _seed(client)
    resp = client.get("/api/v1/stats/summary", params={"pair": "GBPUSD"})
    assert resp.json()["totalTrades"] == 1


def test_stats_charts(client):
    _seed(client)
    resp = client.get("/api/v1/stats/charts")
    assert resp.status_code == 200
    assert "winRateTrend" in resp.json()


def test_stats_strategy_health(client):
    _seed(client)
    resp = client.get("/api/v1/stats/strategy-health")
    assert resp.status_code == 200
    assert "components" in resp.json()


def test_stats_setups(client):
    _seed(client)
    resp = client.get("/api/v1/stats/setups")
    assert resp.status_code == 200
    assert "bestSetup" in resp.json()


def test_stats_mistakes(client):
    _seed(client)
    resp = client.get("/api/v1/stats/mistakes")
    assert resp.status_code == 200
    assert "topMistakes" in resp.json()


def test_stats_summary_empty_journal(client):
    resp = client.get("/api/v1/stats/summary")
    assert resp.status_code == 200
    assert resp.json()["totalTrades"] == 0
