"""调度器层契约（任务列表 / 执行历史 / 手动触发）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JobView(BaseModel):
    """任务视图（含 cron、下次执行时间、上次状态、耗时）。"""

    name: str
    description: str = ""
    cron: str
    timezone: str = "Asia/Shanghai"
    enabled: bool = True
    allow_concurrent: bool = False
    timeout_seconds: int = 900
    max_retries: int = 0
    notifier: str = "file"
    tags: list[str] = Field(default_factory=list)
    next_run_at: str | None = None
    last_status: str | None = None
    last_duration_seconds: float | None = None
    last_finished_at: str | None = None
    last_progress: float | None = None


class JobListBody(BaseModel):
    """任务列表响应体。"""

    jobs: list[JobView]


class RunView(BaseModel):
    """执行记录视图。"""

    run_id: str
    job_name: str
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    progress: float | None = None
    summary: str = ""
    error: str = ""
    attempt: int = 0


class RunListBody(BaseModel):
    """执行历史响应体。"""

    runs: list[RunView]


class TriggerBody(BaseModel):
    """手动触发响应体（返回本次执行的记录）。"""

    job_name: str
    trigger: str = "manual"
    run: RunView


class TriggerRequest(BaseModel):
    """手动触发请求体（可选，缺省即 manual）。"""

    trigger: str = Field("manual", description="触发方式：manual / schedule")
