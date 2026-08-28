"""回测统计指标（纯函数，无副作用）。

提供两类统计：

    - 截面统计：对一批「持有 N 日收益」样本算胜率 / 平均 / 中位数 / 盈亏比 /
      分位数 / 标准差 / 最好最差。
    - 时序统计：对一条净值（或时序收益）算最大回撤与年化夏普。

胜率口径 = 正收益占比（与 top5_verify.py 的 hit_rate 一致）。
盈亏比 = 平均盈利 / |平均亏损|（无亏损样本时记 +inf，用 None 表示）。
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field


def _sorted_values(returns: list[float]) -> list[float]:
    return sorted(returns)


def win_rate(returns: list[float]) -> float:
    """正收益占比（0~1）。空样本返回 0。"""
    if not returns:
        return 0.0
    return sum(1 for r in returns if r > 0) / len(returns)


def profit_loss_ratio(returns: list[float]) -> float | None:
    """盈亏比 = 平均盈利 / |平均亏损|。无亏损样本时返回 None（无法定义）。"""
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    if not wins or not losses:
        return None
    avg_win = sum(wins) / len(wins)
    avg_loss = sum(losses) / len(losses)
    if avg_loss == 0:
        return None
    return avg_win / abs(avg_loss)


def quantile(sorted_values: list[float], q: float) -> float:
    """线性插值分位数（q ∈ [0, 1]）。"""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


@dataclass
class ReturnStats:
    """一批收益样本的截面统计。"""

    n: int = 0
    win_rate: float = 0.0
    avg_return: float = 0.0
    median_return: float = 0.0
    profit_loss_ratio: float | None = None
    std: float = 0.0
    best: float = 0.0
    worst: float = 0.0
    quantiles: dict[str, float] = field(default_factory=dict)


def summarize_returns(returns: list[float]) -> ReturnStats:
    """对一批收益样本算截面统计。空样本返回全 0（n=0）。"""
    if not returns:
        return ReturnStats()

    sv = _sorted_values(returns)
    return ReturnStats(
        n=len(returns),
        win_rate=win_rate(returns),
        avg_return=statistics.fmean(returns),
        median_return=statistics.median(returns),
        profit_loss_ratio=profit_loss_ratio(returns),
        std=statistics.pstdev(returns) if len(returns) > 1 else 0.0,
        best=max(returns),
        worst=min(returns),
        quantiles={
            "p05": round(quantile(sv, 0.05), 6),
            "p25": round(quantile(sv, 0.25), 6),
            "p50": round(quantile(sv, 0.50), 6),
            "p75": round(quantile(sv, 0.75), 6),
            "p95": round(quantile(sv, 0.95), 6),
        },
    )


def equity_curve(returns: list[float], initial: float = 1.0) -> list[float]:
    """由时序收益（按时间顺序）累乘出净值曲线，首项为初始净值。"""
    curve = [initial]
    for r in returns:
        curve.append(curve[-1] * (1.0 + r))
    return curve


def max_drawdown(equity: list[float]) -> float:
    """最大回撤（负值表示回撤幅度，如 -0.2 表示回撤 20%）。

    返回 <= 0 的值；空/单点序列返回 0.0（无回撤）。
    """
    if len(equity) < 2:
        return 0.0
    peak = equity[0]
    worst = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = (v - peak) / peak if peak > 0 else 0.0
        if dd < worst:
            worst = dd
    return worst


def sharpe_ratio(
    period_returns: list[float],
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
) -> float | None:
    """年化夏普 = (年化超额收益) / (年化波动)。

    按「每笔/每期收益」序列计算：均值与标准差各自年化（√periods 缩放波动）。
    样本不足 2 个或波动为 0 时返回 None（无法定义）。
    """
    if len(period_returns) < 2:
        return None
    mean = statistics.fmean(period_returns)
    std = statistics.pstdev(period_returns)
    if std == 0:
        return None
    rf_per_period = risk_free_rate / periods_per_year
    # 年化收益用简单累乘近似（这里用均值×期数近似）
    return (mean - rf_per_period) / std * math.sqrt(periods_per_year)


def total_return(equity: list[float]) -> float:
    """整段净值曲线的总收益（末值 / 首值 - 1）。"""
    if not equity or equity[0] == 0:
        return 0.0
    return equity[-1] / equity[0] - 1.0
