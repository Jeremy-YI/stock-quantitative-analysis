"""调度器服务：薄封装 scheduler.Scheduler，映射成 API 契约。

不碰 HTTP，不直接读文件，所有调度逻辑在 packages/scheduler 里，这里只做
RunRecord / dict → schema 的映射。key 不存在时抛 KeyError，由路由层映射 404。
"""

from __future__ import annotations

from scheduler.scheduler import Scheduler

from schemas.scheduler import JobView, RunView


class SchedulerService:
    """调度器查询 / 触发服务。"""

    def __init__(self, scheduler: Scheduler) -> None:
        self._scheduler = scheduler

    def list_jobs(self) -> list[JobView]:
        return [JobView(**view) for view in self._scheduler.list_jobs()]

    def list_runs(self, job: str | None = None, limit: int = 50) -> list[RunView]:
        records = self._scheduler.list_runs(job=job, limit=limit)
        return [self._to_run_view(r) for r in records]

    def trigger(self, name: str, trigger: str = "manual") -> RunView:
        record = self._scheduler.trigger(name, trigger=trigger)
        return self._to_run_view(record)

    @staticmethod
    def _to_run_view(record) -> RunView:
        return RunView(
            run_id=record.run_id,
            job_name=record.job_name,
            trigger=record.trigger,
            status=record.status.value,
            started_at=record.started_at,
            finished_at=record.finished_at,
            duration_seconds=record.duration_seconds,
            progress=record.progress,
            summary=record.summary,
            error=record.error,
            attempt=record.attempt,
        )
