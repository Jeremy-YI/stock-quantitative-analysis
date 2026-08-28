"""策略层契约（策略列表 / 扫描结果 / 历史信号）。"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel

from strategies.signal import Signal


class StrategyInfo(BaseModel):
    """单个策略的元信息（供 /strategies 列表展示）。"""

    name: str
    description: str
    # 默认阈值（键值对）
    config: dict[str, Any]
    # JSON Schema（含字段中文描述，即「配置说明」）
    config_schema: dict[str, Any]


class StrategyListBody(BaseModel):
    """策略列表响应体。"""

    strategies: list[StrategyInfo]


class ScanBody(BaseModel):
    """单次扫描结果响应体。"""

    strategy: str
    date: date
    signals: list[Signal]


class SignalsBody(BaseModel):
    """历史信号查询响应体。"""

    strategy: str
    signals: list[Signal]
