"""调度器任务实现（A股侧）与注册表组装。

    - ``a_share``      A股任务函数（每日扫描 / 每日报告 / 周度衰减检查）。
    - ``etl``          盘后 ETL（板块 / ETF 资金流、ST 快照）。
    - ``akshare_client`` AKShare 数据客户端（策略层不 import）。
    - ``etl_repository`` / ``sinks`` ETL / 信号落库仓储。
    - ``registry``      A股任务注册表 + 调度栈组装。
"""

from __future__ import annotations

from scheduler.jobs.registry import (
    EXCESS_REFERENCE,
    build_a_share_registry,
    build_engine_decay_provider,
    default_notifier_factory,
)

__all__ = [
    "EXCESS_REFERENCE",
    "build_a_share_registry",
    "build_engine_decay_provider",
    "default_notifier_factory",
]
