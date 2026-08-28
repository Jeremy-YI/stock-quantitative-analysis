"""执行器单测：超时中断 / 重试退避 / 并发跳过 / 进度上报。"""

from __future__ import annotations

import time

from scheduler.executor import JobExecutor, TaskContext
from scheduler.models import JobResult, JobSpec, NotifierKind, RunStatus
from scheduler.notifier import Notifier
from scheduler.repository import InMemoryRunRepository


def _job(name="j", target=None, **overrides) -> JobSpec:
    spec = dict(
        name=name,
        cron="0 9 * * *",
        timeout_seconds=1.0,
        max_retries=0,
        notifier=NotifierKind.FILE,
        target=target or (lambda ctx, **kw: JobResult(summary="ok")),
    )
    spec.update(overrides)
    return JobSpec(**spec)


def test_success_records_run():
    repo = InMemoryRunRepository()
    ex = JobExecutor(repo)
    record = ex.run(_job(target=lambda ctx, **kw: JobResult(summary="done")))
    assert record.status is RunStatus.SUCCESS
    assert record.summary == "done"
    assert record.duration_seconds is not None
    assert repo.latest("j").run_id == record.run_id


def test_failure_records_error():
    repo = InMemoryRunRepository()

    def boom(ctx, **kw):
        raise RuntimeError("boom")

    ex = JobExecutor(repo)
    record = ex.run(_job(target=boom))
    assert record.status is RunStatus.FAILED
    assert "boom" in record.error


def test_timeout_marks_timeout_and_keeps_partial():
    repo = InMemoryRunRepository()

    def slow(ctx: TaskContext, **kw):
        # 先上报进度，然后长时间 sleep（不检查 should_stop，模拟卡死）
        ctx.report_progress(0.5, "已完成一半")
        time.sleep(5)

    ex = JobExecutor(repo, grace_seconds=0.0)
    record = ex.run(_job(target=slow, timeout_seconds=0.3))
    assert record.status is RunStatus.TIMEOUT
    assert record.progress == 0.5
    assert "已完成一半" in record.summary


def test_timeout_graceful_stop_keeps_partial_result():
    repo = InMemoryRunRepository()

    def cooperative(ctx: TaskContext, **kw):
        for i in range(100):
            if ctx.should_stop():
                return JobResult(summary=f"已中断，处理到第 {i} 步")
            time.sleep(0.02)
        return JobResult(summary="全部完成")

    ex = JobExecutor(repo, grace_seconds=2.0)
    record = ex.run(_job(target=cooperative, timeout_seconds=0.1))
    assert record.status is RunStatus.TIMEOUT
    assert "已中断" in record.summary


def test_retry_with_backoff():
    repo = InMemoryRunRepository()
    sleeps: list[float] = []
    attempts = {"n": 0}

    def flaky(ctx, **kw):
        attempts["n"] += 1
        if attempts["n"] <= 2:
            raise RuntimeError("flaky")
        return JobResult(summary="third try ok")

    ex = JobExecutor(repo, sleep=lambda s: sleeps.append(s))
    record = ex.run(_job(target=flaky, max_retries=3, retry_backoff_seconds=10.0))
    assert record.status is RunStatus.SUCCESS
    assert attempts["n"] == 3
    # 指数退避：10 * 2^0, 10 * 2^1
    assert sleeps == [10.0, 20.0]


def test_retry_gives_up_after_max_retries():
    repo = InMemoryRunRepository()
    attempts = {"n": 0}

    def always_fail(ctx, **kw):
        attempts["n"] += 1
        raise RuntimeError("always")

    ex = JobExecutor(repo, sleep=lambda s: None)  # 假 sleep，避免真等退避
    record = ex.run(_job(target=always_fail, max_retries=2))
    assert record.status is RunStatus.FAILED
    assert attempts["n"] == 3  # 首次 + 2 次重试


def test_concurrent_skip():
    repo = InMemoryRunRepository()
    ex = JobExecutor(repo, grace_seconds=0.0)

    started = {"slow_done": False}

    def slow(ctx: TaskContext, **kw):
        # 通过另一个入口触发同任务，模拟并发
        inner = ex.run(_job(target=lambda c, **k: JobResult(summary="x")))
        started["inner_status"] = inner.status.value
        started["slow_done"] = True
        return JobResult(summary="slow done")

    record = ex.run(_job(target=slow))
    assert record.status is RunStatus.SUCCESS
    # 内层触发因为外层还在跑（allow_concurrent=False）被跳过
    assert started["inner_status"] == "skipped"
    assert started["slow_done"] is True


def test_allow_concurrent_runs_both():
    repo = InMemoryRunRepository()
    ex = JobExecutor(repo, grace_seconds=0.0)
    observed = []

    def target(ctx, **kw):
        observed.append(ex.is_running("j"))
        return JobResult(summary="ok")

    record = ex.run(_job(target=target, allow_concurrent=True))
    assert record.status is RunStatus.SUCCESS
    # 内层观察到同任务仍在运行（允许并发）
    assert observed == [True]


def test_emit_report_via_notifier():
    repo = InMemoryRunRepository()
    sent: dict = {}

    class FakeNotifier(Notifier):
        def send(self, job_name, title, content):
            sent["job"] = job_name
            sent["title"] = title
            sent["content"] = content

    def factory(job):
        return FakeNotifier()

    ex = JobExecutor(repo, notifier_factory=factory)
    ex.run(
        _job(
            target=lambda ctx, **kw: JobResult(
                summary="s", report_title="标题", report_markdown="# 正文"
            )
        )
    )
    assert sent["job"] == "j"
    assert sent["title"] == "标题"
    assert sent["content"] == "# 正文"


def test_no_report_when_none():
    repo = InMemoryRunRepository()
    called = {"n": 0}

    def factory(job):
        called["n"] += 1
        return None

    ex = JobExecutor(repo, notifier_factory=factory)
    ex.run(_job(target=lambda ctx, **kw: JobResult(summary="s")))
    # 没有 report_markdown，不应调 notifier 工厂
    assert called["n"] == 0
