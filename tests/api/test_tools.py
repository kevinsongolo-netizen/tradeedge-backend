"""API tests for the Sprint 11 tools router (``/api/v1/tools/*``)."""


def test_position_size_endpoint_basic(client):
    resp = client.post(
        "/api/v1/tools/position-size",
        json={
            "accountBalance": 1000.0,
            "riskPercent": 1.0,
            "entry": 100.0,
            "stopLoss": 98.0,
            "takeProfit": 106.0,
            "valuePerPointPerLot": 10.0,
            "lotStep": 0.01,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["recommendedLots"] == 0.5
    assert body["riskReward"] == 3.0


def test_position_size_endpoint_validation_error(client):
    resp = client.post(
        "/api/v1/tools/position-size",
        json={
            "accountBalance": 1000.0,
            "riskPercent": 1.0,
            "entry": 100.0,
            "stopLoss": 100.0,
            "valuePerPointPerLot": 10.0,
        },
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
