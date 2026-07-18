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


def test_open_then_close_upsert_partial_fields_dont_null_each_other(client):
    """Regression coverage for Sprint 17 (MT5 auto-journal EA): the EA
    posts a trade's open fields when a position opens (no exit/pnl yet
    -- the position isn't closed), then posts again with the SAME id
    and only the close fields (exit/pnl/exitReason) once it closes.
    The second call must not null out entry/sl/tp/direction/pair from
    the first -- upsert() only touches keys actually present in each
    request body (Pydantic's exclude_unset), never the whole row."""
    open_payload = {
        "id": "mt5-12345-987",
        "date": "2026-07-14",
        "pair": "gbpusd",
        "direction": "buy",
        "asset": "Forex",
        "entry": 1.3400,
        "sl": 1.3350,
        "tp": 1.3500,
        "lots": 0.10,
    }
    resp = client.post("/api/v1/trades", json=open_payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["exit"] is None
    assert body["pnl"] is None
    assert body["entry"] == 1.3400

    close_payload = {
        "id": "mt5-12345-987",
        "exit": 1.3480,
        "pnl": 80.0,
        "exitReason": "Take Profit Hit",
    }
    resp = client.post("/api/v1/trades", json=close_payload)
    assert resp.status_code == 201
    body = resp.json()
    # Fields only sent at open time must survive the close-only update.
    assert body["pair"] == "GBPUSD"
    assert body["direction"] == "buy"
    assert body["entry"] == 1.3400
    assert body["sl"] == 1.3350
    assert body["tp"] == 1.3500
    assert body["lots"] == 0.10
    # Fields sent at close time are now populated.
    assert body["exit"] == 1.3480
    assert body["pnl"] == 80.0
    assert body["exitReason"] == "Take Profit Hit"

    fetched = client.get("/api/v1/trades/mt5-12345-987").json()
    assert fetched["exit"] == 1.3480
    assert fetched["entry"] == 1.3400


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


# ---------- Sprint 18: bulk-clear the whole journal ----------

def test_delete_all_without_confirm_phrase_is_422(client):
    client.post("/api/v1/trades", json=SAMPLE)
    resp = client.delete("/api/v1/trades")
    assert resp.status_code == 422
    assert client.get("/api/v1/trades/trade-1").status_code == 200


def test_delete_all_with_wrong_confirm_phrase_is_422(client):
    client.post("/api/v1/trades", json=SAMPLE)
    resp = client.delete("/api/v1/trades", params={"confirm": "yes please"})
    assert resp.status_code == 422
    assert client.get("/api/v1/trades/trade-1").status_code == 200


def test_delete_all_with_correct_confirm_phrase_clears_everything(client):
    items = [{**SAMPLE, "id": f"bulk-{i}", "date": f"2026-02-0{i+1}"} for i in range(3)]
    client.post("/api/v1/trades/bulk", json={"items": items})
    client.post("/api/v1/trades", json=SAMPLE)

    resp = client.delete("/api/v1/trades", params={"confirm": "DELETE ALL MY TRADES"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["deletedCount"] == 4

    listing = client.get("/api/v1/trades").json()
    assert listing["items"] == []


def test_delete_all_on_empty_journal_returns_zero(client):
    resp = client.delete("/api/v1/trades", params={"confirm": "DELETE ALL MY TRADES"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["deletedCount"] == 0


# --- Sprint 20 Phase 3 -- screenshots + trade detail insight ---------------


def test_create_trade_with_structured_screenshots_round_trips(client):
    payload = {
        **SAMPLE,
        "id": "trade-screenshots",
        "screenshots": [
            {"url": "https://res.cloudinary.com/demo/image/upload/v1/tradeedge/entry.png", "kind": "entry"},
            {"url": "https://res.cloudinary.com/demo/image/upload/v1/tradeedge/exit.png", "kind": "exit"},
        ],
    }
    resp = client.post("/api/v1/trades", json=payload)
    assert resp.status_code == 201, resp.text
    shots = resp.json()["screenshots"]
    assert len(shots) == 2
    assert shots[0]["kind"] == "entry"
    assert shots[1]["kind"] == "exit"

    fetched = client.get("/api/v1/trades/trade-screenshots").json()
    assert len(fetched["screenshots"]) == 2


def test_trade_screenshots_default_to_empty_list_when_omitted(client):
    payload = {**SAMPLE, "id": "trade-no-screenshots"}
    resp = client.post("/api/v1/trades", json=payload)
    assert resp.status_code == 201, resp.text
    assert resp.json()["screenshots"] == []


def test_trade_detail_insight_404s_for_unknown_trade(client):
    resp = client.get("/api/v1/trades/does-not-exist/insight")
    assert resp.status_code == 404


def test_trade_detail_insight_has_no_lesson_for_a_still_open_trade(client):
    open_trade = {**SAMPLE, "id": "trade-open"}
    del open_trade["exit"]
    resp = client.post("/api/v1/trades", json=open_trade)
    assert resp.status_code == 201, resp.text

    insight_resp = client.get("/api/v1/trades/trade-open/insight")
    assert insight_resp.status_code == 200, insight_resp.text
    body = insight_resp.json()
    assert body["lesson"] is None
    assert "insight" in body
    assert "narrative" in body["insight"]


def test_trade_detail_insight_has_a_lesson_for_a_closed_trade(client):
    resp = client.post("/api/v1/trades", json={**SAMPLE, "id": "trade-closed"})
    assert resp.status_code == 201, resp.text

    insight_resp = client.get("/api/v1/trades/trade-closed/insight")
    assert insight_resp.status_code == 200, insight_resp.text
    body = insight_resp.json()
    assert body["lesson"] is not None
    assert body["lesson"]["outcome"] in ("Win", "Loss", "Breakeven", "Unknown")
    assert "lessons" in body["lesson"]


def test_trade_detail_insight_excludes_the_trade_itself_from_its_own_history(client):
    # A trade can't be "similar to itself" -- similarity search must
    # exclude the candidate's own id from the history it's compared
    # against (regression coverage for the shared search_similar id check).
    resp = client.post("/api/v1/trades", json={**SAMPLE, "id": "trade-self-exclude"})
    assert resp.status_code == 201, resp.text

    insight_resp = client.get("/api/v1/trades/trade-self-exclude/insight")
    assert insight_resp.status_code == 200, insight_resp.text
    for top in insight_resp.json()["insight"]["topSimilar"]:
        assert top["id"] != "trade-self-exclude"
