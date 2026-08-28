"""执行器：跑任务 + 超时 / 重试 / 并发控制 / 进度上报。

核心语义（对应任务书「解决超时问题」）：

    - 每个任务声明自己的超时预算（``JobSpec.timeout_seconds``），超时后**优雅
      中断**：先 ``TaskContext.request_stop()``，给一段宽限期让任务自己收尾
      （分片任务在片间检查 ``should_stop()``），记录已完成的部分，而不是整个失败。
    - 失败（抛异常）按 ``max_retries`` 指数退避重试；超时不重试（预算已耗尽）。
    - 并发控制：同一任务上一次没跑完（``allow_concurrent=False``）就跳过本次，
      记录一条 ``skipped``。
    - 进度上报：任务通过 ``ctx.report_progress(pct, note)`` 写进执行记录，
      前端能看到跑到百分之几。

任务函数签名约定：``target(ctx: TaskContext, **kwargs) -> JobResult``。
执行在守护线程里跑（超时后不阻塞主流程），通过 ``thread.join(timeout)`` 实现
协作式超时，不依赖可强杀的进程模型。
"""

from __future__ import annotations

import threading
import traceback
from typing import Callable
from uuid import uuid4

from scheduler.cron import now
from scheduler.models import JobResult, JobSpec, RunRecord, RunStatus
from scheduler.notifier import Notifier
from scheduler.repository import RunRepository

# 超时后给任务自己收尾的宽限期（秒）；任务应在这段时间内检查 should_stop 并退出
DEFAULT_GRACE_SECONDS = 2.0

_MAX_SUMMARY = 500
_MAX_ERROR = 2000


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "…（已截断）"


class TaskContext:
    """任务执行上下文：进度上报 + 协作式中断信号。"""

    def __init__(self, on_progress: Callable[[float, str], None] | None = None) -> None:
        self._stop = threading.Event()
        self._on_progress = on_progress
        self.progress: float = 0.0
        self.note: str = ""

    def report_progress(self, pct: float, note: str = "") -> None:
        """上报进度（0~1）与说明；同时回调给执行器更新记录。"""
        self.progress = max(0.0, min(1.0, pct))
        self.note = note
        if self._on_progress is not None:
            self._on_progress(self.progress, note)

    def should_stop(self) -> bool:
        """任务应在长循环/片间检查此方法，返回 True 表示被要求中断。"""
        return self._stop.is_set()

    def request_stop(self) -> None:
        """（执行器调用）请求任务停止。"""
        self._stop.set()


# notifier 工厂：给定任务，返回其报告输出器（可为 None 表示不输出）
NotifierFactory = Callable[[JobSpec], Notifier | None]


class JobExecutor:
    """任务执行器。"""

    def __init__(
        self,
        run_repo: RunRepository,
        notifier_factory: NotifierFactory | None = None,
        clock: Callable[[], object] | None = None,
        sleep: Callable[[float], None] | None = None,
        grace_seconds: float = DEFAULT_GRACE_SECONDS,
    ) -> None:
        self._run_repo = run_repo
        self._notifier_factory = notifier_factory or (lambda _job: None)
        self._clock = clock or now
        self._sleep = sleep or _default_sleep
        self._grace_seconds = grace_seconds
        self._running: set[str] = set()
        self._lock = threading.Lock()

    def is_running(self, job_name: str) -> bool:
        with self._lock:
            return job_name in self._running

    # ------------------------------------------------------------------
    def run(self, job: JobSpec, trigger: str = "schedule") -> RunRecord:
        """执行一次任务（含并发控制 / 重试 / 落库 / 通知），返回执行记录。"""
        # 并发控制：上次没跑完就跳过（除非允许并发）
        with self._lock:
            if job.name in self._running and not job.allow_concurrent:
                record = RunRecord(
                    run_id=uuid4().hex,
                    job_name=job.name,
                    trigger=trigger,
                    status=RunStatus.SKIPPED,
                    started_at=self._clock(),
                    finished_at=self._clock(),
                    summary="上次执行尚未完成，跳过本次（allow_concurrent=False）",
                )
                self._run_repo.save(record)
                return record
            self._running.add(job.name)

        try:
            record, result = self._run_with_retry(job, trigger)
        finally:
            with self._lock:
                self._running.discard(job.name)

        self._run_repo.save(record)

        # 成功后按任务声明的渠道发报告
        if record.status is RunStatus.SUCCESS and result is not None:
            self._emit(job, result)

        return record

    # ------------------------------------------------------------------
    def _run_with_retry(self, job: JobSpec, trigger: str) -> tuple[RunRecord, JobResult | None]:
        attempt = 0
        while True:
            record, result = self._attempt(job, attempt, trigger)
            # 超时不重试（预算已耗尽），成功不重试
            if record.status in (RunStatus.SUCCESS, RunStatus.TIMEOUT):
                return record, result
            if attempt >= job.max_retries:
                return record, result
            delay = job.retry_backoff_seconds * (2 ** attempt)
            self._sleep(delay)
            attempt += 1

    def _attempt(
        self, job: JobSpec, attempt: int, trigger: str
    ) -> tuple[RunRecord, JobResult | None]:
        started = self._clock()
        record = RunRecord(
            run_id=uuid4().hex,
            job_name=job.name,
            trigger=trigger,
            status=RunStatus.SUCCESS,
            started_at=started,
            attempt=attempt,
        )

        def on_progress(pct: float, note: str) -> None:
            record.progress = pct
            if note:
                record.summary = _truncate(note, _MAX_SUMMARY)

        ctx = TaskContext(on_progress=on_progress)

        result_holder: dict = {}

        def worker() -> None:
            try:
                result_holder["result"] = job.target(ctx, **job.kwargs)
            except Exception as exc:  # noqa: BLE001 — 捕获一切异常记入记录
                result_holder["error"] = exc

        thread = threading.Thread(target=worker, daemon=True, name=f"job-{job.name}")
        thread.start()
        thread.join(timeout=job.timeout_seconds)

        if thread.is_alive():
            # 超时：先优雅中断，给宽限期让任务自己收尾
            ctx.request_stop()
            thread.join(timeout=self._grace_seconds)
            record.status = RunStatus.TIMEOUT
            if thread.is_alive():
                record.error = _truncate(
                    f"执行超时（预算 {job.timeout_seconds}s），已请求中断，"
                    "任务未在宽限期内退出，记录已完成部分",
                    _MAX_ERROR,
                )
            else:
                # 中断成功：尽量保留任务返回的部分摘要
                res = result_holder.get("result")
                if isinstance(res, JobResult):
                    record.summary = _truncate(res.summary, _MAX_SUMMARY)
                record.error = _truncate(
                    f"执行超时（预算 {job.timeout_seconds}s），已优雅中断", _MAX_ERROR
                )
        elif "error" in result_holder:
            record.status = RunStatus.FAILED
            record.error = _truncate(
                traceback.format_exception_only(
                    type(result_holder["error"]), result_holder["error"]
                )[-1].strip(),
                _MAX_ERROR,
            )
            if record.summary == "":
                record.summary = "执行失败"
        else:
            result = result_holder.get("result")
            if isinstance(result, JobResult):
                record.summary = _truncate(result.summary, _MAX_SUMMARY)
            record.status = RunStatus.SUCCESS

        finished = self._clock()
        record.finished_at = finished
        record.duration_seconds = round(_seconds_between(started, finished), 3)

        result = result_holder.get("result")
        return record, (result if isinstance(result, JobResult) else None)

    def _emit(self, job: JobSpec, result: JobResult) -> None:
        """把成功任务生成的报告按 notifier 渠道发出去。"""
        if result.report_markdown is None:
            return
        notifier = self._notifier_factory(job)
        if notifier is not None:
            notifier.send(
                job.name,
                result.report_title or job.name,
                result.report_markdown,
            )


def _default_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


def _seconds_between(start, finish) -> float:
    """计算两个 datetime 的秒差（naive 或 aware 都能处理）。"""
    try:
        return (finish - start).total_seconds()
    except TypeError:
        # 一个是 naive 一个是 aware 时兜底为 0（测试里 clock 可能返回 naive）
        return 0.0
