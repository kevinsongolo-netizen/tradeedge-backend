"""Tests for the position sizing calculator engine (Sprint 11)."""
import pytest

from app.engines.position_size_engine import calculate_position_size


def _base_req(**overrides):
    req = {
        "account_balance": 1000.0,
        "risk_percent": 1.0,
        "risk_amount": None,
        "entry": 100.0,
        "stop_loss": 98.0,
        "take_profit": 106.0,
        "value_per_point_per_lot": 10.0,
        "lot_step": 0.01,
    }
    req.update(overrides)
    return req


def test_basic_calculation():
    result = calculate_position_size(_base_req())
    # risk_amount = 1000 * 1% = 10; price_distance = 2; raw_lots = 10 / (2*10) = 0.5
    assert result["risk_amount"] == 10.0
    assert result["price_distance"] == 2.0
    assert result["recommended_lots"] == 0.5
    assert result["actual_risk_amount"] == pytest.approx(10.0)
    assert result["warnings"] == []


def test_take_profit_gives_risk_reward_and_potential_profit():
    result = calculate_position_size(_base_req())
    # reward_distance = 6, risk_reward = 6/2 = 3.0
    assert result["risk_reward"] == pytest.approx(3.0)
    assert result["potential_profit"] == pytest.approx(0.5 * 6 * 10.0)


def test_direct_risk_amount_overrides_percent():
    result = calculate_position_size(_base_req(risk_amount=50.0, risk_percent=None))
    assert result["risk_amount"] == 50.0
    # 50 / (2*10) = 2.5 lots
    assert result["recommended_lots"] == 2.5


def test_rounds_down_to_lot_step():
    # raw lots = 10 / (2*10) = 0.5 exactly with step 0.01 -> stays 0.5;
    # use a case that doesn't land on a clean step.
    result = calculate_position_size(_base_req(risk_amount=11.0, risk_percent=None, lot_step=0.1))
    # raw = 11/20 = 0.55 -> floor to nearest 0.1 -> 0.5
    assert result["recommended_lots"] == pytest.approx(0.5)


def test_zero_lots_warns_instead_of_erroring():
    result = calculate_position_size(_base_req(risk_amount=0.01, risk_percent=None, lot_step=0.01))
    assert result["recommended_lots"] == 0.0
    assert any("rounds down to 0" in w for w in result["warnings"])


def test_high_risk_percent_warns():
    result = calculate_position_size(_base_req(risk_percent=5.0, risk_amount=None))
    assert any("high" in w for w in result["warnings"])


@pytest.mark.parametrize(
    "overrides,message_fragment",
    [
        ({"account_balance": 0}, "Account balance"),
        ({"entry": 100.0, "stop_loss": 100.0}, "same price"),
        ({"value_per_point_per_lot": 0}, "value_per_point_per_lot"),
        ({"lot_step": 0}, "Lot step"),
        ({"risk_percent": None, "risk_amount": None}, "Provide either"),
    ],
)
def test_invalid_input_raises(overrides, message_fragment):
    req = _base_req(**overrides)
    with pytest.raises(ValueError, match=message_fragment):
        calculate_position_size(req)
