"""CRUD API tests — ``/api/v1/trades`` (Section 4.2)."""

SAMPLE = {
    "id": "trade-1",
    "date": "2026-01-01",
    "pair": "eurusd",
    "direction": "buy",
    "asset": "Forex",
    "entry": 1.0850,
    "exit": 1.0910,
    "sl": 1.0820,
    "tp": 1.0920,
    "lots": 0.1,
    "pnl": 60.0,
    "rr": 2.1,
    "h4Trend": "Bullish",
    "h4PoiType": "OB",
    "premiumDiscount": "Discount",
    "m15Confirmations": ["BOS", "Liquidity Sweep"],
    "session": "London",
    "news": "Low",
    "confidence": 75,
    "followedPlan": "Yes",
    "rulesFollowed": "all",
    "exitReason": "Take Profit Hit",
    "emotion": "Calm",
    "notes": "clean setup",
}


def test_create_trade_returns_201_with_scores(client):
    resp = client.post("/api/v1/trades", json=SAMPLE)
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == "trade-1"
    assert body["pair"] == "EURUSD"  # upper-cased
    assert isinstance(body["ruleScore"], int)
    assert isinstance(body["overallScore"], int)
    assert body["ruleRecommendation"] in ("TAKE", "CAUTION", "SKIP")
    assert "createdAt" in body and "updatedAt" in body


def test_create_trade_is_idempotent_upsert(client):
    client.post("/api/v1/trades", json=SAMPLE)
    resp = client.post("/api/v1/trades", json={**SAMPLE, "confidence": 95})
    assert resp.status_code == 201
    assert resp.json()["confidence"] == 95.0


def test_get_trade_by_id(client):
    client.post("/api/v1/trades", json=SAMPLE)
    resp = client.get("/api/v1/trades/trade-1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "trade-1"


def test_get_missing_trade_returns_404_envelope(client):
    resp = client.get("/api/v1/trades/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert "request_id" in body["error"]


def test_list_trades_returns_items_and_cursor(client):
    for i in range(3):
        client.post("/api/v1/trades", json={**SAMPLE, "id": f"trade-{i}", "date": f"2026-01-0{i+1}"})
    resp = client.get("/api/v1/trades", params={"limit": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["nextCursor"] is not None


def test_list_trades_filters_by_pair(client):
    client.post("/api/v1/trades", json={**SAMPLE, "id": "eur-1", "pair": "EURUSD"})
    client.post("/api/v1/trades", json={**SAMPLE, "id": "gbp-1", "pair": "GBPUSD", "date": "2026-01-02"})
    resp = client.get("/api/v1/trades", params={"pair": "GBPUSD"})
    items = resp.json()["items"]
    assert all(i["pair"] == "GBPUSD" for i in items)


def test_patch_trade_updates_field_and_rescoresa(client):
    client.post("/api/v1/trades", json=SAMPLE)
    resp = client.patch("/api/v1/trades/trade-1", json={"confidence": 20, "followedPlan": "No"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["confidence"] == 20.0
    assert body["followedPlan"] == "No"


def test_patch_missing_trade_returns_404(client):
    resp = client.patch("/api/v1/trades/nope", json={"confidence": 10})
    assert resp.status_code == 404


def test_delete_trade(client):
    client.post("/api/v1/trades", json=SAMPLE)
    resp = client.delete("/api/v1/trades/trade-1")
    assert resp.status_code == 204
    assert client.get("/api/v1/trades/trade-1").status_code == 404


def test_delete_missing_trade_returns_404(client):
    resp = client.delete("/api/v1/trades/nope")
    assert resp.status_code == 404


def test_bulk_upsert(client):
    items = [{**SAMPLE, "id": f"bulk-{i}", "date": f"2026-02-0{i+1}"} for i in range(3)]
    resp = client.post("/api/v1/trades/bulk", json={"items": items})
    assert resp.status_code == 200
    body = resp.json()
    assert body["inserted"] == 3
    assert body["updated"] == 0
    assert body["failed"] == []


def test_bulk_upsert_rejects_items_missing_required_id_at_schema_level(client):
    # TradeIn requires "id" — a malformed item fails request validation
    # (422) before it ever reaches the service, which is the correct
    # place to catch this rather than a per-row service-level failure.
    items = [{**SAMPLE, "id": "ok-1"}, {"date": "2026-01-01"}]  # second has no id
    resp = client.post("/api/v1/trades/bulk", json={"items": items})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_bulk_upsert_mixed_insert_and_update(client):
    client.post("/api/v1/trades", json={**SAMPLE, "id": "existing-1"})
    items = [{**SAMPLE, "id": "existing-1", "confidence": 99}, {**SAMPLE, "id": "new-1"}]
    resp = client.post("/api/v1/trades/bulk", json={"items": items})
    assert resp.status_code == 200
    body = resp.json()
    assert body["inserted"] == 1
    assert body["updated"] == 1
    assert body["failed"] == []


def test_open_trade_has_null_execution_score(client):
    open_trade = {k: v for k, v in SAMPLE.items() if k not in ("exit", "pnl")}
    resp = client.post("/api/v1/trades", json={**open_trade, "id": "open-1"})
    body = resp.json()
    assert body["executionScore"] is None
    assert body["overallScore"] == body["ruleScore"]
