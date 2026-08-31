"""回测 API 集成测试：发起 / 查询 / 衰减（200 / 404 / 422）。"""

from __future__ import annotations

from datetime import date

import httpx
import pandas as pd
import pytest

from config.settings import Settings
from main import create_app
from repositories.backtest_repository import InMemoryBacktestRunRepository
from tests.helpers import make_candle_df


async def _wait_done(client: httpx.AsyncClient, run_id: str) -> dict:
    """轮询直到回测完成（异步执行，POST 立即返回，结果要等后台线程）。"""
    import asyncio

    for _ in range(200):  # 最多约 10s
        res = await client.get(f"/api/v1/backtest/runs/{run_id}")
        job = res.json()["body"]
        if job["status"] in ("done", "failed"):
            return job
        await asyncio.sleep(0.05)
    raise AssertionError("回测任务超时未完成")


def _decline_candles() -> dict[str, pd.DataFrame]:
    """一只持续下跌的标的（触发 B1 超卖），供 fake 扫描器返回。"""
    closes = [100 * (0.98**i) for i in range(60)]
    return {"600000": make_candle_df(closes, start=date(2026, 1, 5))}


class FakeScanner:
    """内存版扫描器：返回预置 candles，忽略过滤配置。"""

    def __init__(self, candles: dict[str, pd.DataFrame]) -> None:
        self._candles = candles

    def load_candles(self, as_of, filter_config=None):
        return self._candles


@pytest.fixture()
async def client():
    app = create_app(
        Settings(hsjday_root="/tmp"),
        repository=None,
        strategy_scanner=FakeScanner(_decline_candles()),
        scan_repository=None,
        backtest_repository=InMemoryBacktestRunRepository(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_create_run_verify_200(client):
    res = await client.post(
        "/api/v1/backtest/runs",
        json={
            "strategy": "b1b2b3",
            "start": "2026-01-20",
            "end": "2026-01-30",
            "mode": "verify",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["message"] == "ok"
    job = body["body"]
    assert job["run_id"]
    assert job["strategy"] == "b1b2b3"
    # status 是瞬态（后台线程可能已经跑完，也可能还在 queued/running），
    # 只断言是合法状态之一，不赌时序
    assert job["status"] in ("queued", "running", "done")

    run = await _wait_done(client, job["run_id"])
    assert run["status"] == "done"
    report = run["report"]
    assert report["verification"]["total_signals"] >= 0
    assert report["verification"]["hold_days"]
    assert report["portfolio"] is None  # verify 模式不跑组合


async def test_create_run_portfolio_200(client):
    res = await client.post(
        "/api/v1/backtest/runs",
        json={
            "strategy": "b1b2b3",
            "start": "2026-01-20",
            "end": "2026-01-30",
            "mode": "portfolio",
        },
    )
    assert res.status_code == 200
    job = res.json()["body"]
    run = await _wait_done(client, job["run_id"])
    assert run["report"]["portfolio"] is not None


async def test_get_run_200_and_404(client):
    created = await client.post(
        "/api/v1/backtest/runs",
        json={"strategy": "b1b2b3", "start": "2026-01-20", "end": "2026-01-30", "mode": "verify"},
    )
    run_id = created.json()["body"]["run_id"]

    res = await client.get(f"/api/v1/backtest/runs/{run_id}")
    assert res.status_code == 200
    assert res.json()["body"]["run_id"] == run_id

    missing = await client.get("/api/v1/backtest/runs/nope")
    assert missing.status_code == 404
    assert "detail" in missing.json()


async def test_create_run_404_unknown_strategy(client):
    res = await client.post(
        "/api/v1/backtest/runs",
        json={"strategy": "nope", "start": "2026-01-20", "end": "2026-01-30", "mode": "verify"},
    )
    assert res.status_code == 404


async def test_create_run_422_invalid_date(client):
    res = await client.post(
        "/api/v1/backtest/runs",
        json={"strategy": "b1b2b3", "start": "not-a-date", "end": "2026-01-30", "mode": "verify"},
    )
    assert res.status_code == 422


async def test_create_run_400_start_after_end(client):
    res = await client.post(
        "/api/v1/backtest/runs",
        json={"strategy": "b1b2b3", "start": "2026-01-30", "end": "2026-01-20", "mode": "verify"},
    )
    assert res.status_code == 400


async def test_decay_200(client):
    res = await client.get(
        "/api/v1/backtest/decay",
        params={
            "strategy": "b1b2b3",
            "window": 20,
            "start": "2026-01-20",
            "end": "2026-01-30",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["message"] == "ok"
    assert body["body"]["strategy"] == "b1b2b3"
    assert body["body"]["window"] == 20


async def test_decay_404_unknown_strategy(client):
    res = await client.get(
        "/api/v1/backtest/decay", params={"strategy": "nope", "window": 20}
    )
    assert res.status_code == 404
