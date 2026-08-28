"""概览页 API 集成测试：快照有数据 / 快照缺失降级（httpx.AsyncClient）。"""

from __future__ import annotations

import json

import httpx
import pytest

from config.settings import Settings
from main import create_app
from scheduler.executor import JobExecutor
from scheduler.models import JobResult, JobSpec, NotifierKind
from scheduler.registry import JobRegistry
from scheduler.repository import InMemoryRunRepository
from scheduler.scheduler import Scheduler


def _make_scheduler() -> Scheduler:
    registry = JobRegistry()

    def noop(ctx, **kw):
        return JobResult(summary="ok")

    registry.register(
        JobSpec(name="daily_scan", cron="30 15 * * 1-5", target=noop, notifier=NotifierKind.FILE)
    )
    run_repo = InMemoryRunRepository()
    executor = JobExecutor(run_repo)
    return Scheduler(registry, executor, run_repo)


def _snapshot() -> dict:
    return {
        "as_of": "2026-08-27",
        "strategies": [
            {
                "name": "stealth_rally",
                "description": "水下二次金叉",
                "signals_today": 1263,
                "selectivity": 0.152,
                "excess_win_rate": 0.068,
                "hold_days": 20,
            }
        ],
        "baselines": [
            {
                "universe": "stock",
                "size": 5510,
                "holds": [{"hold_days": 1, "win_rate": 0.467, "avg_return": -0.0009}],
            }
        ],
        "last_scan": {"status": "ok", "as_of": "2026-08-27", "duration_seconds": 45.2, "symbols_scanned": 6968},
    }


def _client(snapshot_path, tmp_path):
    app = create_app(
        Settings(hsjday_root="/tmp", dashboard_snapshot_path=str(snapshot_path)),
        scheduler_instance=_make_scheduler(),
    )
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_overview_200_with_snapshot(tmp_path):
    snapshot_path = tmp_path / "dashboard_snapshot.json"
    snapshot_path.write_text(json.dumps(_snapshot()), encoding="utf-8")

    async with _client(snapshot_path, tmp_path) as client:
        res = await client.get("/api/v1/dashboard/overview")

    assert res.status_code == 200
    body = res.json()["body"]
    assert body["as_of"] == "2026-08-27"
    assert body["strategies"][0]["name"] == "stealth_rally"
    assert body["strategies"][0]["excess_win_rate"] == 0.068
    assert body["baselines"][0]["universe"] == "stock"
    assert body["last_scan"]["symbols_scanned"] == 6968
    # recent_runs 来自注入的 fake scheduler，初始为空
    assert body["recent_runs"] == []


@pytest.mark.asyncio
async def test_overview_200_without_snapshot_degrades(tmp_path):
    # 快照缺失时降级为空，不报错
    async with _client(tmp_path / "missing.json", tmp_path) as client:
        res = await client.get("/api/v1/dashboard/overview")

    assert res.status_code == 200
    body = res.json()["body"]
    assert body["strategies"] == []
    assert body["baselines"] == []
    assert body["last_scan"] is None
