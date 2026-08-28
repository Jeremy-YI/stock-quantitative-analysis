"""stock-scheduler：任务调度器（阶段 5）。

目标：把 Jeremy 现有那 16 个 cron 里属于 A股侧的任务，迁移成声明式任务 +
执行器 + 断点续跑 + 盘后 ETL，解决「15 分钟硬超时打满」的痛点。

核心设计：

    - 声明式任务定义：``JobSpec`` 用 pydantic 描述一个任务（名称 / cron 表达式 /
      执行目标 / 超时 / 重试 / 输出渠道 / 是否允许并发）。
    - 执行器 ``JobExecutor``：跑任务、处理超时（优雅中断 + 记录已完成部分）、
      指数退避重试、并发跳过、进度上报。
    - 执行记录落库：``RunRecord`` 记录每次执行的开始/结束/状态/耗时/摘要/错误。
    - 断点续跑：``ShardTracker`` 把标的宇宙分片，每片独立记录完成状态，
      中断后下次只跑未完成的片。
    - 时区固定 Asia/Shanghai，cron 解析用 croniter（不自己写）。

本包不依赖 apps/api（反向依赖），任务落库用本包自己的仓储（MySQL 表结构与
apps/api/migrations 对齐），任务实现见 ``scheduler.jobs``。
"""

from __future__ import annotations

from scheduler.cron import next_run, parse_cron
from scheduler.executor import JobExecutor, TaskContext
from scheduler.models import JobResult, JobSpec, NotifierKind, RunRecord, RunStatus
from scheduler.notifier import FileNotifier, Notifier, WebhookNotifier
from scheduler.registry import JobRegistry
from scheduler.repository import (
    InMemoryRunRepository,
    MySqlRunRepository,
    RunRepository,
)
from scheduler.scheduler import Scheduler
from scheduler.sharding import InMemoryShardTracker, MySqlShardTracker, ShardTracker

__all__ = [
    "FileNotifier",
    "InMemoryRunRepository",
    "InMemoryShardTracker",
    "JobExecutor",
    "JobRegistry",
    "JobResult",
    "JobSpec",
    "MySqlRunRepository",
    "MySqlShardTracker",
    "Notifier",
    "NotifierKind",
    "RunRecord",
    "RunRepository",
    "RunStatus",
    "Scheduler",
    "ShardTracker",
    "TaskContext",
    "WebhookNotifier",
    "next_run",
    "parse_cron",
]
