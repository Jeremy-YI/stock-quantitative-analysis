"""任务注册表：按名查找 / 列出全部任务。

职责单一：只管注册与查询，不做调度。任务名全局唯一，重复注册抛错，
避免两个 cron 静默覆盖。
"""

from __future__ import annotations

from scheduler.models import JobSpec


class JobRegistry:
    """任务注册表（进程内 dict，启动时一次性注册）。"""

    def __init__(self) -> None:
        self._jobs: dict[str, JobSpec] = {}

    def register(self, job: JobSpec) -> None:
        """注册一个任务；同名重复注册抛 ``ValueError``。"""
        if job.name in self._jobs:
            raise ValueError(f"任务 {job.name} 已注册，不能重复注册")
        self._jobs[job.name] = job

    def get(self, name: str) -> JobSpec:
        """按名取任务；不存在抛 ``KeyError``。"""
        if name not in self._jobs:
            raise KeyError(f"任务 {name} 不存在")
        return self._jobs[name]

    def has(self, name: str) -> bool:
        return name in self._jobs

    def list(self) -> list[JobSpec]:
        """按注册名排序返回全部任务（含禁用的）。"""
        return [self._jobs[n] for n in sorted(self._jobs)]

    def names(self) -> list[str]:
        return sorted(self._jobs)
