"""调度器数据模型：声明式任务定义 + 执行记录 + 任务结果。

``JobSpec`` 是任务声明的唯一事实来源（名字 / cron / 超时 / 重试 / 并发 /
输出渠道 / 执行目标）。``RunRecord`` 是每次执行的落库记录。``JobResult`` 是
任务函数返回给执行器的结构化结果（摘要 + 可选报告）。

约定：所有字段用 camelCase 落库（与 API 输出对齐，Jeremy 个人口味），
但 pydantic 字段名本身用 snake_case，序列化时通过 ``model_dump`` 的
``by_alias`` 控制（见 API schema 层）。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field


class RunStatus(str, Enum):
    """一次执行的状态。"""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class NotifierKind(str, Enum):
    """任务报告输出渠道。"""

    FILE = "file"
    WEBHOOK = "webhook"


class JobSpec(BaseModel):
    """声明式任务定义。

    target 是执行目标（``Callable[[TaskContext, ...], JobResult]``），不参与
    序列化，仅在运行期由执行器调用；kwargs 是传给 target 的静态参数。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(..., description="任务唯一名（注册表按名查找）")
    description: str = Field("", description="任务说明")
    cron: str = Field(..., description="cron 表达式（5 段，时区固定 Asia/Shanghai）")
    timeout_seconds: float = Field(
        900.0, description="单次执行超时预算（秒，支持小数，方便测试）"
    )
    max_retries: int = Field(0, description="失败后重试次数（0=不重试）")
    retry_backoff_seconds: float = Field(
        30.0, description="重试指数退避的基数（秒）"
    )
    allow_concurrent: bool = Field(
        False, description="是否允许同一任务重叠执行（False=上次没跑完就跳过）"
    )
    notifier: NotifierKind = Field(
        NotifierKind.FILE, description="报告输出渠道：file / webhook"
    )
    enabled: bool = Field(True, description="是否启用（禁用的任务不参与调度）")
    tags: list[str] = Field(default_factory=list, description="分组标签，如 A股/美股")
    # 执行目标：函数 + 静态参数。函数不可序列化，仅运行期使用。
    target: Callable[..., Any] | None = Field(
        None, exclude=True, description="执行目标函数（运行期注入，不落库）"
    )
    kwargs: dict[str, Any] = Field(
        default_factory=dict, description="传给 target 的静态参数"
    )


class JobResult(BaseModel):
    """任务函数返回给执行器的结构化结果。

    report_markdown / report_title 存在时，执行器会按 JobSpec.notifier 的渠道
    把报告发出去；summary 写进执行记录的摘要字段（截断）。
    """

    summary: str = Field("", description="执行结果一句话摘要")
    report_title: str | None = Field(None, description="报告标题")
    report_markdown: str | None = Field(None, description="报告正文（Markdown）")


class RunRecord(BaseModel):
    """一次执行记录（落库）。"""

    run_id: str = Field(..., description="执行 id（UUID）")
    job_name: str = Field(..., description="任务名")
    trigger: str = Field("schedule", description="触发方式：schedule / manual")
    status: RunStatus = Field(..., description="执行状态")
    started_at: datetime = Field(..., description="开始时间（Asia/Shanghai）")
    finished_at: datetime | None = Field(None, description="结束时间")
    duration_seconds: float | None = Field(None, description="耗时（秒）")
    progress: float | None = Field(None, description="进度 0~1")
    summary: str = Field("", description="输出摘要（截断）")
    error: str = Field("", description="错误堆栈（截断）")
    attempt: int = Field(0, description="第几次尝试（0 起）")
