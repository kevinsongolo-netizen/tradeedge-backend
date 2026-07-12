"""Similar-trade API tests — ``POST /api/v1/ai/similar`` (Section 4.4)."""

BASE_TRADE = {
    "date": "2026-01-01", "pair": "EURUSD", "direction": "buy", "asset": "Forex",
    "entry": 1.08, "exit": 1.09, "pnl": 60.0, "rr": 2.0, "session": "London",
    "h4Trend": "Bullish", "h4PoiType": "OB", "confidence": 80,
}


def test_similar_finds_matches_from_history(client):
    for i in range(3):
        client.post("/api/v1/trades", json={**BASE_TRADE, "id": f"hist-{i}"})
    resp = client.post(
        "/api/v1/ai/similar",
        json={"candidate": BASE_TRADE, "minSimilarity": 50, "limit": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["similar"]) == 3
    assert body["algorithm"] == "weighted-v1"
    assert body["winRate"] == 100.0


def test_similar_respects_min_similarity(client):
    client.post("/api/v1/trades", json={**BASE_TRADE, "id": "match-1"})
    client.post(
        "/api/v1/trades",
        json={**BASE_TRADE, "id": "nomatch-1", "pair": "BTCUSD", "asset": "Crypto", "session": "Asian", "h4Trend": "Bearish", "rr": 0.2},
    )
    resp = client.post("/api/v1/ai/similar", json={"candidate": BASE_TRADE, "minSimilarity": 90})
    assert resp.status_code == 200
    ids = [m["id"] for m in resp.json()["similar"]]
    assert "nomatch-1" not in ids


def test_similar_legacy_algorithm(client):
    client.post("/api/v1/trades", json={**BASE_TRADE, "id": "hist-legacy"})
    resp = client.post("/api/v1/ai/similar", json={"candidate": BASE_TRADE, "algorithm": "legacy"})
    assert resp.status_code == 200
    assert resp.json()["algorithm"] == "legacy"


def test_similar_empty_history_returns_empty(client):
    resp = client.post("/api/v1/ai/similar", json={"candidate": BASE_TRADE})
    assert resp.status_code == 200
    assert resp.json()["similar"] == []


def test_similar_candidate_structure_fields_actually_affect_score(client):
    """Regression test for a bug found during Sprint 8: the /ai/similar
    router used to pass candidate.to_model_kwargs() (snake_case) into
    search_similar(), which reads camelCase keys (h4Trend, h4PoiType,
    premiumDiscount, m15Confirmations) — so every SMC-structure feature
    (worth ~44 of the algorithm's 100 weight points) was silently
    excluded from every similarity score. A history trade sharing only
    the "easy" fields (pair/direction/asset/session) with a completely
    different market structure should NOT score 100% similar."""
    candidate = {
        "date": "2026-01-05", "pair": "EURUSD", "direction": "buy", "asset": "Forex", "session": "London",
        "h4Trend": "Bullish", "h4PoiType": "Order Block", "premiumDiscount": "Discount",
        "m15Confirmations": ["BOS", "CHOCH"], "rr": 2.5, "confidence": 80,
    }
    structurally_different = {
        **candidate,
        "id": "structurally-different",
        "h4Trend": "Bearish", "h4PoiType": "FVG", "premiumDiscount": "Premium",
        "m15Confirmations": [],
    }
    client.post("/api/v1/trades", json=structurally_different)

    resp = client.post(
        "/api/v1/ai/similar",
        json={"candidate": candidate, "minSimilarity": 0, "limit": 10},
    )
    assert resp.status_code == 200
    matches = resp.json()["similar"]
    assert len(matches) == 1
    assert matches[0]["similarity"] < 90, (
        "structurally different trade scored too high a similarity — "
        "H4 trend/POI/premium-discount/M15 confirmations aren't being "
        "compared"
    )
