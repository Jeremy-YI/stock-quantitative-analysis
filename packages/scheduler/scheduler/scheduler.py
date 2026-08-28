"""调度器编排层：把注册表 + 执行器 + 仓储串起来。

对外提供：
    - ``list_jobs`` / ``get_job``：任务列表（含 cron、下次执行时间、上次状态）。
    - ``trigger``：手动触发（或调度循环触发）。
    - ``list_runs``：执行历史。
    - ``run_due``：扫描并执行「到点」的任务（供进程内循环 / 测试用）。

不负责「起一个常驻循环进程」——那是运行入口（见 scheduler/jobs/registry.py
里的 run 入口，或部署文档），本类保持纯业务逻辑可单测。
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from scheduler.cron import next_run, now
from scheduler.executor import JobExecutor
from scheduler.models import JobSpec, RunRecord
from scheduler.registry import JobRegistry
from scheduler.repository import RunRepository


def _aware(dt: datetime) -> datetime:
    """把 naive datetime 归一化到上海时区（容错调用方）。"""
    if dt.tzinfo is None:
        from scheduler.cron import TZ

        return dt.replace(tzinfo=TZ)
    return dt


class Scheduler:
    """任务编排器。"""

    def __init__(
        self,
        registry: JobRegistry,
        executor: JobExecutor,
        run_repo: RunRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._registry = registry
        self._executor = executor
        self._run_repo = run_repo
        self._clock = clock or now

    def list_jobs(self) -> list[dict]:
        """任务列表（含下次执行时间 / 上次状态 / 耗时）。"""
        out: list[dict] = []
        for job in self._registry.list():
            latest = self._run_repo.latest(job.name)
            out.append(self._job_view(job, latest))
        return out

    def get_job(self, name: str) -> dict:
        """单任务视图（含下次执行时间 / 上次状态）。"""
        job = self._registry.get(name)  # 不存在抛 KeyError
        return self._job_view(job, self._run_repo.latest(name))

    def _job_view(self, job: JobSpec, latest: RunRecord | None) -> dict:
        try:
            nxt = next_run(job.cron)
        except ValueError:
            nxt = None
        return {
            "name": job.name,
            "description": job.description,
            "cron": job.cron,
            "timezone": "Asia/Shanghai",
            "enabled": job.enabled,
            "allow_concurrent": job.allow_concurrent,
            "timeout_seconds": job.timeout_seconds,
            "max_retries": job.max_retries,
            "notifier": job.notifier.value,
            "tags": job.tags,
            "next_run_at": nxt.isoformat() if nxt else None,
            "last_status": latest.status.value if latest else None,
            "last_duration_seconds": latest.duration_seconds if latest else None,
            "last_finished_at": (
                latest.finished_at.isoformat() if latest and latest.finished_at else None
            ),
            "last_progress": latest.progress if latest else None,
        }

    def trigger(self, name: str, trigger: str = "manual") -> RunRecord:
        """触发一次任务（manual / schedule）。"""
        job = self._registry.get(name)  # 不存在抛 KeyError
        return self._executor.run(job, trigger=trigger)

    def list_runs(self, job: str | None = None, limit: int = 50) -> list[RunRecord]:
        """执行历史（时间倒序）。"""
        return self._run_repo.list(job=job, limit=limit)

    def run_due(self, now: datetime | None = None) -> list[RunRecord]:
        """执行所有「到点」的启用任务，返回触发的执行记录列表。

        到点判定：该任务自上次执行结束时间（无记录则以 now 为锚）以来的下一次
        cron 触发时间 <= now。
        """
        now = _aware(now or self._clock())
        triggered: list[RunRecord] = []
        for job in self._registry.list():
            if not job.enabled:
                continue
            latest = self._run_repo.latest(job.name)
            if latest is not None:
                anchor = latest.finished_at or latest.started_at
            else:
                anchor = now
            try:
                nxt = next_run(job.cron, after=_aware(anchor))
            except ValueError:
                continue
            if nxt <= now:
                triggered.append(self.trigger(job.name, trigger="schedule"))
        return triggered
