"""回测结果模型（pydantic，供 API JSON 序列化 + 前端展示）。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class HoldReturn(BaseModel):
    """单个持有期的收益统计。

    baseline_* / excess_* 为「同期同宇宙基线」对比项（阶段 4.5 引入）：
        excess_win_rate = win_rate - baseline_win_rate（超额胜率）
        excess_return  = avg_return - baseline_avg_return（超额收益）
    基线为空（未提供宇宙/区间）时这些字段为 None，表示无法计算超额。
    """

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
    histogram: list[dict] = Field(default_factory=list)
    # 同期同宇宙基线（个股/ETF 分开），无基线时为 None
    baseline_win_rate: float | None = None
    baseline_avg_return: float | None = None
    excess_win_rate: float | None = None
    excess_return: float | None = None


class BaselineHold(BaseModel):
    """单个持有期的基线统计。"""

    hold_days: int
    n: int = 0
    win_rate: float = 0.0
    avg_return: float = 0.0
    median_return: float = 0.0


class BaselineResult(BaseModel):
    """某个标的宇宙（个股 / ETF）的基线结果。"""

    universe: str
    size: int = 0
    holds: list[BaselineHold] = Field(default_factory=list)


class StrategyResult(BaseModel):
    """某策略各持有期的表现（含选择性指标）。

    signals_per_day = 日均信号数；selectivity = 日均信号数 / 宇宙标的数
    （即每天触发了该宇宙的百分之几，衡量策略的「筛选作用」强弱）。
    """

    strategy: str
    universe: str | None = None
    universe_size: int | None = None
    signals_per_day: float | None = None
    selectivity: float | None = None
    holds: list[HoldReturn] = Field(default_factory=list)


class BoardResult(BaseModel):
    """某板块各持有期的表现（简化板块 = 市场板块）。"""

    board: str
    holds: list[HoldReturn] = Field(default_factory=list)


class DecayPoint(BaseModel):
    """衰减曲线上的一个点（某日滚动窗口胜率）。

    baseline_win_rate / excess_win_rate 为同期市场基线对比（阶段 4.5 引入）：
    excess_win_rate = win_rate - baseline_win_rate。基线不可得时为 None。
    """

    date: date
    window: int
    win_rate: float
    n: int
    baseline_win_rate: float | None = None
    excess_win_rate: float | None = None


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
    baselines: list[BaselineResult] = Field(default_factory=list)


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


class BacktestReport(BaseModel):
    """一次回测的完整报告（信号验证 + 可选组合净值）。"""

    verification: VerificationReport
    portfolio: PortfolioReport | None = None
