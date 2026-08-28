"""概览页契约（Dashboard 首页聚合数据）。"""

from __future__ import annotations

from pydantic import BaseModel

from schemas.scheduler import RunView


class DashboardStrategy(BaseModel):
    """单个策略在概览页的展示数据。"""

    name: str
    description: str = ""
    # 快照日（as_of）当天的信号数
    signals_today: int = 0
    # 选择性 = 日均信号数 / 宇宙标的数（0~1，越小筛选越强）
    selectivity: float | None = None
    # 超额胜率（相对同期同宇宙基线，pp 已折算成小数，正负用前端 up/down 色）
    excess_win_rate: float | None = None
    # 该超额胜率对应的持有期（交易日）
    hold_days: int = 20


class DashboardBaselineHold(BaseModel):
    """单个持有期的市场基线（随机持有 N 日正收益比例）。"""

    hold_days: int
    win_rate: float = 0.0
    avg_return: float = 0.0


class DashboardBaseline(BaseModel):
    """某个标的宇宙（个股 / ETF）的市场基线。"""

    universe: str
    size: int = 0
    holds: list[DashboardBaselineHold] = []


class DashboardLastScan(BaseModel):
    """最近一次全市场扫描的状态（来自调度器 daily_scan 的执行记录）。"""

    status: str = "unknown"
    as_of: str | None = None
    duration_seconds: float | None = None
    symbols_scanned: int | None = None


class DashboardRegime(BaseModel):
    """当前市场环境（regime）快照（见 market.regime 与 docs/市场环境模块说明.md）。"""

    as_of: str | None = None
    index_20d_return: float | None = None  # 大盘 20 日涨跌
    activity: float | None = None  # 市场活跃度（总量/60日均量）
    drawdown: float | None = None  # 距 120 日高点回撤（≤ 0）
    index_20d_label: str = ""
    activity_label: str = ""
    drawdown_label: str = ""
    allow_open: bool | None = None  # 默认 filter 下是否允许开仓


class DashboardOverview(BaseModel):
    """概览页聚合数据。"""

    as_of: str | None = None
    strategies: list[DashboardStrategy] = []
    baselines: list[DashboardBaseline] = []
    last_scan: DashboardLastScan | None = None
    regime: DashboardRegime | None = None
    recent_runs: list[RunView] = []
