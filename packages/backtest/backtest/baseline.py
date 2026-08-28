"""基线计算：给定标的宇宙 + 日期区间 + 持有期，算「随机持有 N 日」的
正收益比例与平均收益，供策略胜率做超额对比。

方法论要点（这是阶段 4.5 的关键修正，见 docs/回测迁移说明.md）：

    - 股票的正收益比例基线**不是 50%**（掷硬币），而是取决于市场本身。
      2026-03-01 ~ 2026-08-27 全市场个股基线 1 日正收益比例实测只有 46.6%，
      且随持有期拉长单调下滑（20 日 41.7%）。用 50% 当基准会把「跑赢市场
      但在 50% 以下的策略」误判成坏策略（stealth_rally 就是被误伤的）。
    - **个股与 ETF 的基线必须分开算**：ETF 波动小于个股，其基线不同，
      不能混用。ETF 策略对 ETF 基线，个股策略对个股基线。
    - 基线口径 = 该宇宙内每个标的在区间内每个交易日的 close[T+N]/close[T]-1
      的截面正收益占比（等价于「随机某天买入、持有 N 日」的期望胜率）。

纯函数、无副作用，可独立单测。依赖 numpy/pandas 做向量化前向收益，
避免 5510 只个股 × 124 日 × 5 持有期的逐样本 Python 循环。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Collection, Sequence

import numpy as np
import pandas as pd


@dataclass
class BaselineHoldStats:
    """单个持有期的基线统计（纯函数层，供引擎转成 models.BaselineHold）。"""

    hold_days: int
    n: int = 0
    win_rate: float = 0.0
    avg_return: float = 0.0
    median_return: float = 0.0


@dataclass
class BaselineResultStats:
    """某个标的宇宙（个股 / ETF）的基线结果（纯函数层）。"""

    universe: str
    size: int = 0  # 宇宙标的数（= 参与计算基线的代码个数）
    holds: list[BaselineHoldStats] = field(default_factory=list)


def _valid_entries(
    df: pd.DataFrame, start: date, end: date
) -> tuple[np.ndarray, np.ndarray]:
    """返回 (日期列表, 收盘价数组)，仅保留 date 列落在 [start, end] 内的行。"""
    if df is None or df.empty:
        return np.array([], dtype=object), np.array([], dtype=float)

    in_range = df["date"].between(start, end).to_numpy(dtype=bool)
    idxs = np.nonzero(in_range)[0]
    if idxs.size == 0:
        return np.array([], dtype=object), np.array([], dtype=float)

    dates = df["date"].to_numpy()[idxs]
    closes = df["close"].astype(float).to_numpy()[idxs]
    return dates, closes


def compute_baseline(
    candles: dict[str, pd.DataFrame],
    symbols: Collection[str],
    universe: str,
    start: date,
    end: date,
    hold_days: Sequence[int],
) -> BaselineResultStats:
    """算一个标的宇宙在区间内的「随机持有 N 日」基线。

    Args:
        candles: {代码: 全量日线 DataFrame}，需含 date/close 列（按日期升序）。
        symbols: 该宇宙的代码集合（只在这些标的上算基线）。
        universe: 宇宙标识（"stock" / "etf"），仅用于结果标注。
        start / end: 买入区间（闭区间，交易日）。
        hold_days: 持有期（交易日）列表。

    Returns:
        BaselineResultStats，其中每个持有期给出 n / win_rate / avg_return /
        median_return。正收益比例 win_rate 即「同期同宇宙的基线胜率」。
    """
    ret_arrays: dict[int, list[np.ndarray]] = {hd: [] for hd in hold_days}

    for symbol in symbols:
        df = candles.get(symbol)
        if df is None or df.empty:
            continue
        closes_full = df["close"].astype(float).to_numpy()
        n_full = len(closes_full)
        if n_full == 0:
            continue

        in_range = df["date"].between(start, end).to_numpy(dtype=bool)
        idxs = np.nonzero(in_range)[0]
        if idxs.size == 0:
            continue

        for hd in hold_days:
            j = idxs + hd
            valid = j < n_full
            if not valid.any():
                continue
            jj = j[valid]
            ii = idxs[valid]
            base = closes_full[ii]
            ok = base > 0
            if not ok.any():
                continue
            rets = closes_full[jj[ok]] / base[ok] - 1.0
            ret_arrays[hd].append(rets)

    holds: list[BaselineHoldStats] = []
    for hd in hold_days:
        arr = np.concatenate(ret_arrays[hd]) if ret_arrays[hd] else np.empty(0)
        holds.append(
            BaselineHoldStats(
                hold_days=hd,
                n=int(arr.size),
                win_rate=float((arr > 0).mean()) if arr.size else 0.0,
                avg_return=float(arr.mean()) if arr.size else 0.0,
                median_return=float(np.median(arr)) if arr.size else 0.0,
            )
        )

    return BaselineResultStats(universe=universe, size=len(symbols), holds=holds)


def daily_baseline_win_rates(
    candles: dict[str, pd.DataFrame],
    symbols: Collection[str],
    start: date,
    end: date,
    hold_days: Sequence[int],
) -> dict[int, dict[date, float]]:
    """按交易日算每个持有期的「当日基线正收益占比」（市场广度口径）。

    用于把策略衰减曲线从「原始胜率」改成「超额胜率」——某天全市场都在跌时，
    策略原始胜率下降只是市场变差，不是策略失效；减去当日基线才能看出真假。

    Returns:
        {hold_days: {date: 当日基线胜率}}。某日没有任何标的可算则该日缺失。
    """
    wins: dict[int, dict[date, int]] = {hd: defaultdict(int) for hd in hold_days}
    counts: dict[int, dict[date, int]] = {hd: defaultdict(int) for hd in hold_days}

    for symbol in symbols:
        df = candles.get(symbol)
        if df is None or df.empty:
            continue
        closes = df["close"].astype(float).to_numpy()
        dates = df["date"].to_numpy()
        n = len(closes)
        if n == 0:
            continue

        in_range = df["date"].between(start, end).to_numpy(dtype=bool)
        for i in np.nonzero(in_range)[0]:
            base = closes[i]
            if base <= 0:
                continue
            d = dates[i]
            for hd in hold_days:
                j = i + hd
                if j >= n:
                    continue
                r = closes[j] / base - 1.0
                counts[hd][d] += 1
                if r > 0:
                    wins[hd][d] += 1

    out: dict[int, dict[date, float]] = {}
    for hd in hold_days:
        out[hd] = {
            d: wins[hd][d] / counts[hd][d] for d in counts[hd] if counts[hd][d] > 0
        }
    return out
