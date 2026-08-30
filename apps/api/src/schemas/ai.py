"""AI 解读契约。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from strategies.signal import Signal


class InterpretBody(BaseModel):
    """AI 解读请求：一只票 + 扫描日。"""

    symbol: str
    date: date


class InterpretResult(BaseModel):
    """AI 解读响应：这只票触发的信号 + 自然语言解读。"""

    symbol: str
    signals: list[Signal]
    interpretation: str
