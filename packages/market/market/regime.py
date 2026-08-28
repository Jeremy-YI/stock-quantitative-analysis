"""市场环境（regime）模块。

从全市场日线计算三个环境指标，输出离散分档标签，供组合回测做 regime 过滤：

    1. 等权指数收益序列 + 20 日涨跌（r20）——大盘趋势方向。
    2. 市场活跃度 = 当日总成交量 / 过去 60 日平均总成交量（activity）。
    3. 距 120 日高点回撤（drawdown，≤ 0，负值表示低于高点）。

实测依据（/tmp/regime_test.py，529,497 样本，2023-01 ~ 2026-08，持有 5 日）：
    区间基线胜率在 42%~68% 之间波动（26pp 差异），远大于任何选股策略的
    超额（+7~14pp），**择时的价值大于选股**。默认 filter 采用「均值回归组合
    （水下多头 + vr60<0.6）超额为正」的市场状态：大盘 20 日涨幅 < +4%、
    活跃度 < 1.2、回撤在 -15%~0。详见 docs/市场环境模块说明.md。

本模块是纯函数 + dataclass，不依赖 pydantic（保持 market 包零依赖），
组合回测侧的参数化封装在 ``backtest.config.RegimeFilterConfig``。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Iterable

import numpy as np
import pandas as pd

# 等权指数序列所需的最少有效标的数（低于此视为该日样本不足，剔除）
_MIN_SYMBOLS_PER_DAY = 50

# 分档边界（与 /tmp/regime_test.py 一致，见 docs/市场环境模块说明.md）
_R20_BINS = (-0.10, -0.04, 0.0, 0.04, 0.10)
_R20_LABELS = ("强跌<-10%", "弱跌-10~-4%", "微跌-4~0", "微涨0~4%", "上涨4~10%", "强涨>10%")
_ACTIVITY_BINS = (0.8, 1.0, 1.2, 1.5)
_ACTIVITY_LABELS = ("清淡<0.8", "偏淡0.8-1.0", "正常1.0-1.2", "活跃1.2-1.5", "火爆>1.5")
_DRAWDOWN_BINS = (-0.25, -0.15, -0.08, -0.03)
_DRAWDOWN_LABELS = ("深跌<-25%", "中跌-25~-15%", "浅跌-15~-8%", "近高-8~-3%", "新高区-3~0")


def _bin_label(value: float | None, bins: Iterable[float], labels: tuple[str, ...]) -> str:
    """按 [bins] 升序边界把 value 分进 labels（labels 长度 = len(bins)+1）。"""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "无数据"
    for bound, label in zip(bins, labels):
        if value < bound:
            return label
    return labels[-1]


def classify_regime(
    index_20d_return: float | None,
    activity: float | None,
    drawdown: float | None,
) -> dict[str, str]:
    """把三个环境指标映射成离散分档标签。

    返回 dict：
        index_20d  大盘 20 日涨跌分档
        activity   市场活跃度分档
        drawdown   距 120 日高点回撤分档
    """
    return {
        "index_20d": _bin_label(index_20d_return, _R20_BINS, _R20_LABELS),
        "activity": _bin_label(activity, _ACTIVITY_BINS, _ACTIVITY_LABELS),
        "drawdown": _bin_label(drawdown, _DRAWDOWN_BINS, _DRAWDOWN_LABELS),
    }


@dataclass(frozen=True)
class RegimeSnapshot:
    """某交易日的市场环境快照。"""

    date: date
    index_20d_return: float
    activity: float
    drawdown: float

    @property
    def labels(self) -> dict[str, str]:
        return classify_regime(
            self.index_20d_return, self.activity, self.drawdown
        )


def compute_market_series(
    candles: dict[str, pd.DataFrame], min_symbols: int = _MIN_SYMBOLS_PER_DAY
) -> pd.DataFrame:
    """从全市场日线计算等权市场序列。

    Args:
        candles: {6 位代码: 日线 DataFrame}（含 date/close/volume 列）。
        min_symbols: 某日有效标的数低于此值则剔除该日（默认 50，可降用于单测）。

    Returns:
        以 date 为索引、按日期升序的 DataFrame，列：
            mret      当日等权平均收益（close[i]/close[i-1]-1，跨标的算术平均）
            mvol      当日总成交量（手）
            idx       等权指数（(1+mret) 累乘）
            r20       等权指数近 20 个交易日涨跌幅
            drawdown  等权指数相对近 120 日最高点的回撤（≤ 0）
            activity  当日总成交量 / 过去 60 日平均总成交量
        数据不足时返回空 DataFrame（无这些列）。
    """
    # 日期 -> [当日收益和, 有效标的数, 当日成交量和]
    agg: dict[date, list[float]] = defaultdict(lambda: [0.0, 0, 0.0])
    for _symbol, df in candles.items():
        if df is None or len(df) < 2:
            continue
        dcol = "date" if "date" in df.columns else df.columns[0]
        dates = pd.to_datetime(df[dcol]).dt.date.tolist()
        closes = pd.to_numeric(df["close"], errors="coerce").tolist()
        vols = pd.to_numeric(df["volume"], errors="coerce").tolist()
        for i in range(1, len(closes)):
            prev = closes[i - 1]
            cur = closes[i]
            if not prev or not cur or prev <= 0:
                continue
            day = dates[i]
            cell = agg[day]
            cell[0] += cur / prev - 1.0
            cell[1] += 1
            cell[2] += float(vols[i]) if vols[i] and vols[i] == vols[i] else 0.0

    rows = [
        (d, ret_sum / n, vol_sum)
        for d, (ret_sum, n, vol_sum) in agg.items()
        if n >= min_symbols
    ]
    if not rows:
        return pd.DataFrame()

    ms = (
        pd.DataFrame(rows, columns=["date", "mret", "mvol"])
        .sort_values("date")
        .reset_index(drop=True)
    )
    ms["idx"] = (1.0 + ms["mret"]).cumprod()
    ms["r20"] = ms["idx"].pct_change(20)
    ms["drawdown"] = ms["idx"] / ms["idx"].rolling(120, min_periods=40).max() - 1.0
    ms["activity"] = ms["mvol"] / ms["mvol"].rolling(60, min_periods=20).mean()
    return ms.set_index("date")


def snapshot_at(series: pd.DataFrame, day: date) -> RegimeSnapshot | None:
    """取某交易日的市场环境快照；无数据（NaN / 缺日）返回 None。"""
    if series is None or series.empty or day not in series.index:
        return None
    row = series.loc[day]
    r20 = _as_float(row["r20"])
    activity = _as_float(row["activity"])
    drawdown = _as_float(row["drawdown"])
    if r20 is None or activity is None or drawdown is None:
        return None
    return RegimeSnapshot(
        date=day,
        index_20d_return=r20,
        activity=activity,
        drawdown=drawdown,
    )


def _as_float(value) -> float | None:
    """安全转 float：None / NaN 返回 None。"""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(f):
        return None
    return f


# ── 策略类型 → regime 过滤档（阶段 9：分策略配置，替代全局一刀切） ──
#
# 阶段 8 实测发现默认 filter 对「均值回归类」有效、对「深跌吸筹类」有害：
#   - 均值回归类（水下多头 + 极缩量等）：避开强涨 / 火爆 / 深跌，要清淡市。
#   - 深跌吸筹类（ETF 跌幅 25%-40% + 底背离）：恰恰需要深回撤才能触发，
#     默认 filter 的 min_drawdown=-15% 会把它的买点全部挡掉。
# 因此把 regime 条件按策略类型分开声明（见各策略 config 的 regime_profile 字段）。
REGIME_PROFILES: dict[str, dict[str, float]] = {
    # 均值回归类：大盘 20 日涨幅 < +4% 且 活跃度 < 1.2 且 回撤在 -15%~0。
    "mean_reversion": {
        "max_index_20d_return": 0.04,
        "max_activity": 1.2,
        "min_drawdown": -0.15,
        "max_drawdown": 0.0,
    },
    # 深跌吸筹类：允许深回撤（下界放到 -40%，对应 ETF 跌幅 25%-40% 的甜点区），
    # 同时避开暴涨市（大盘 20 日涨幅 < +10%）与极端火爆（活跃度 < 1.5）。
    "deep_accumulation": {
        "max_index_20d_return": 0.10,
        "max_activity": 1.5,
        "min_drawdown": -0.40,
        "max_drawdown": 0.0,
    },
}


def profile_params(profile: str | None) -> dict[str, float] | None:
    """返回策略类型对应的 regime 过滤参数；未知 / None 返回 None（不过滤）。"""
    if not profile:
        return None
    return REGIME_PROFILES.get(profile)


def should_allow(
    index_20d_return: float | None,
    activity: float | None,
    drawdown: float | None,
    *,
    max_index_20d_return: float = 0.04,
    max_activity: float = 1.2,
    min_drawdown: float = -0.15,
    max_drawdown: float = 0.0,
) -> bool:
    """判断某日市场环境是否允许开仓（默认 filter 见 docs/市场环境模块说明.md）。

    任一指标缺失 / NaN 时返回 False（数据不足默认保守不允许）。
    """
    r20 = _as_float(index_20d_return)
    act = _as_float(activity)
    dd = _as_float(drawdown)
    if r20 is None or act is None or dd is None:
        return False
    return (
        r20 < max_index_20d_return
        and act < max_activity
        and min_drawdown <= dd <= max_drawdown
    )
