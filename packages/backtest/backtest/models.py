"""回测结果模型（pydantic，供 API JSON 序列化 + 前端展示）。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class HoldReturn(BaseModel):
    """单个持有期的收益统计。"""

    hold_days: int
    n: int = 0
    win_rate: float = 0.0
    avg_return: float = 0.0
    median_return: float = 0.0
    profit_loss_ratio: float | None = None
    std: float = 0.0
    best: float = 0.0
    worst: float = 0.0
    quantiles: dict[str, float] = Field(default_factory=dict)


class StrategyResult(BaseModel):
    """某策略各持有期的表现。"""

    strategy: str
    holds: list[HoldReturn] = Field(default_factory=list)


class BoardResult(BaseModel):
    """某板块各持有期的表现（简化板块 = 市场板块）。"""

    board: str
    holds: list[HoldReturn] = Field(default_factory=list)


class DecayPoint(BaseModel):
    """衰减曲线上的一个点（某日滚动窗口胜率）。"""

    date: date
    window: int
    win_rate: float
    n: int


class DecaySeries(BaseModel):
    """某策略的衰减曲线。"""

    strategy: str
    hold_days: int
    window: int
    points: list[DecayPoint] = Field(default_factory=list)


class VerificationReport(BaseModel):
    """信号验证模式报告。"""

    as_of_hint: str = ""
    total_signals: int = 0
    hold_days: list[int] = Field(default_factory=list)
    by_strategy: list[StrategyResult] = Field(default_factory=list)
    by_board: list[BoardResult] = Field(default_factory=list)
    decay: list[DecaySeries] = Field(default_factory=list)


class EquityPoint(BaseModel):
    """净值曲线上的一个点。"""

    date: str
    equity: float


class PortfolioReport(BaseModel):
    """组合回测报告。"""

    equity_curve: list[EquityPoint] = Field(default_factory=list)
    total_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe: float | None = None
    trade_count: int = 0
    filled_buys: int = 0
    skipped_buys: int = 0
    open_positions: int = 0
