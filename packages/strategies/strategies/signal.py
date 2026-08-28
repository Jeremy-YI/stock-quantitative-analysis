"""选股信号模型（五个策略共用的统一返回格式）。

每个策略暴露一致的签名：:

    def scan(candles: dict[str, DataFrame], as_of: date, config: XxxConfig) -> list[Signal]

``Signal`` 用 pydantic 建模，字段语义：

    symbol        6 位 A股代码
    strategy      策略名（如 "b1b2b3" / "macd_resonance"）
    signal_type   该策略内的信号子类型（如 "b2" / "pin30"）
    score         打分，供排序与看板展示（越大越优先）
    triggered_at  触发日（= 扫描日 as_of）
    metrics       明细指标（键值对，浮点已做确定性舍入，便于快照测试）
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

# metrics 的取值类型（浮点/整数/字符串/布尔/空值，保证 JSON 可序列化）
MetricValue = float | int | str | bool | None


class Signal(BaseModel):
    """一条选股信号。"""

    symbol: str
    strategy: str
    signal_type: str
    score: float
    triggered_at: date
    metrics: dict[str, MetricValue] = Field(default_factory=dict)
