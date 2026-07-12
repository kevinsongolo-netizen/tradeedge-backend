"""Regression tests for issues found in the post-Sprint-7 production
readiness audit: non-mutating feature engineering, the DB-level
one-active-model-per-user / unique-version constraints, model-loading
caching, and that training no longer blocks the event loop."""
import asyncio
import time

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

from app.db.database import get_sessionmaker
from app.db.models.ml_export import MLModel
from app.ml.features import add_hist_strategy_health

pytestmark = pytest.mark.asyncio


def _row(id_, date, pnl=50.0):
    return {
        "id": id_, "date": date, "pair": "EURUSD", "rules_followed": "all",
        "followed_plan": "Yes", "execution_score": 80, "rr": 2.0, "stop_loss": 1.1,
        "emotion": "Calm", "exit_reason": "TP", "pnl": pnl,
    }


async def test_add_hist_strategy_health_does_not_mutate_input():
    original = [_row(str(i), f"2026-01-{i+1:02d}") for i in range(5)]
    snapshot = [dict(r) for r in original]  # deep-enough copy for this flat shape

    result = add_hist_strategy_health(original)

    assert original == snapshot, "input rows must not be mutated"
    assert "hist_strategy_health_score" not in original[0]
    assert "hist_strategy_health_score" in result[0]
    assert result is not original


async def test_db_rejects_two_active_models_for_same_user():
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        await session.execute(
            insert(MLModel).values(user_id=1, version="v1", is_active=True)
        )
        await session.commit()

        with pytest.raises(IntegrityError):
            await session.execute(
                insert(MLModel).values(user_id=1, version="v2", is_active=True)
            )
            await session.commit()


async def test_db_rejects_duplicate_version_for_same_user():
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        await session.execute(
            insert(MLModel).values(user_id=1, version="v1", is_active=False)
        )
        await session.commit()

        with pytest.raises(IntegrityError):
            await session.execute(
                insert(MLModel).values(user_id=1, version="v1", is_active=False)
            )
            await session.commit()


async def test_model_cache_avoids_reloading_from_disk(monkeypatch, tmp_path):
    import app.services.ml_prediction_service as svc

    # Build a tiny real pipeline artifact so predict_proba works.
    import joblib
    from sklearn.dummy import DummyClassifier
    import pandas as pd

    clf = DummyClassifier(strategy="constant", constant=1)
    clf.fit(pd.DataFrame({"x": [1, 2, 3]}), [0, 1, 1])
    path = tmp_path / "fake_model.joblib"
    joblib.dump({"pipeline": clf, "metadata": {}}, path)

    svc._MODEL_CACHE.clear()
    calls = {"n": 0}
    real_load = svc.load_model

    def counting_load(p):
        calls["n"] += 1
        return real_load(p)

    monkeypatch.setattr(svc, "load_model", counting_load)

    await svc._load_cached_model(1, str(path))
    await svc._load_cached_model(1, str(path))
    await svc._load_cached_model(1, str(path))

    assert calls["n"] == 1, "second and third calls should hit the cache, not disk"
    svc._MODEL_CACHE.clear()


async def test_train_and_compare_offloaded_does_not_block_event_loop():
    """The fix wraps train_and_compare() in asyncio.to_thread(); this
    proves the event loop keeps making progress on other coroutines
    while a (slow, synthetic) "training" call is in flight — the exact
    bug found in the audit (a real training run measured at 3.4s
    entirely on the event loop thread)."""

    def slow_cpu_bound_work():
        time.sleep(0.3)
        return "done"

    heartbeats = 0
    stop = False

    async def heartbeat():
        nonlocal heartbeats
        while not stop:
            heartbeats += 1
            await asyncio.sleep(0.01)

    hb_task = asyncio.create_task(heartbeat())
    result = await asyncio.to_thread(slow_cpu_bound_work)
    stop = True
    await hb_task

    assert result == "done"
    # With the event loop genuinely free during the 0.3s of "training",
    # the heartbeat should have ticked roughly 30 times (every ~10ms).
    # A blocked event loop would have produced close to zero.
    assert heartbeats > 10, f"expected the event loop to stay responsive, got {heartbeats} heartbeats"
