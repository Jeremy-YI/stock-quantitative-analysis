"""调度器 API 集成测试：200 / 404 / 422（httpx.AsyncClient + ASGITransport）。"""

from __future__ import annotations

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
    registry.register(
        JobSpec(name="daily_report", cron="0 16 * * 1-5", target=noop, notifier=NotifierKind.WEBHOOK)
    )
    run_repo = InMemoryRunRepository()
    executor = JobExecutor(run_repo)
    return Scheduler(registry, executor, run_repo)


@pytest.fixture()
async def client():
    app = create_app(
        Settings(hsjday_root="/tmp"),
        scheduler_instance=_make_scheduler(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_jobs_200(client):
    res = await client.get("/api/v1/scheduler/jobs")
    assert res.status_code == 200
    body = res.json()
    assert body["message"] == "ok"
    jobs = body["body"]["jobs"]
    names = {j["name"] for j in jobs}
    assert {"daily_scan", "daily_report"} <= names
    # 每个任务都带 cron / 下次执行时间
    for j in jobs:
        assert j["cron"]
        assert j["next_run_at"]


async def test_trigger_200(client):
    res = await client.post("/api/v1/scheduler/jobs/daily_scan/trigger")
    assert res.status_code == 200
    body = res.json()
    assert body["body"]["job_name"] == "daily_scan"
    assert body["body"]["run"]["status"] == "success"


async def test_trigger_404_unknown_job(client):
    res = await client.post("/api/v1/scheduler/jobs/nope/trigger")
    assert res.status_code == 404
    assert "message" in res.json()


async def test_runs_200_after_trigger(client):
    await client.post("/api/v1/scheduler/jobs/daily_scan/trigger")
    res = await client.get("/api/v1/scheduler/runs")
    assert res.status_code == 200
    runs = res.json()["body"]["runs"]
    assert len(runs) >= 1
    assert runs[0]["job_name"] == "daily_scan"
    assert runs[0]["status"] == "success"


async def test_runs_filter_by_job(client):
    await client.post("/api/v1/scheduler/jobs/daily_scan/trigger")
    res = await client.get("/api/v1/scheduler/runs", params={"job": "daily_report"})
    assert res.status_code == 200
    assert res.json()["body"]["runs"] == []


async def test_runs_422_invalid_limit(client):
    res = await client.get("/api/v1/scheduler/runs", params={"limit": 0})
    assert res.status_code == 422
