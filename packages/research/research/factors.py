"""因子分析函数：单因子超额 / 因子交叉矩阵（纯函数，作用于 DataFrame）。"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _win_rate(series: pd.Series) -> float:
    """正收益占比（NaN 已由调用方剔除）。"""
    if len(series) == 0:
        return 0.0
    return float((series > 0).mean())


def _base(frame: pd.DataFrame, ret_col: str, baseline: float | None) -> float:
    """基线胜率：显式传入则用之，否则用整表正收益占比。"""
    if baseline is not None:
        return baseline
    return _win_rate(frame[ret_col].dropna())


def excess_by_bins(
    frame: pd.DataFrame,
    value_col: str,
    bins: list[float],
    labels: list[str],
    ret_col: str = "ret",
    baseline: float | None = None,
) -> pd.DataFrame:
    """按数值分档算单因子超额。

    Args:
        frame: 因子长表（含 value_col 与 ret_col）。
        value_col: 数值因子列名。
        bins: ``pd.cut`` 的分箱边界（升序，含最右开区间）。
        labels: 分箱标签（长度 = len(bins)-1）。
        ret_col: 收益列名（默认 ret）。
        baseline: 基线胜率（None = 整表正收益占比）。

    Returns:
        DataFrame，列：label / n / win_rate / avg_return / excess_win_rate /
        excess_return。excess_win_rate 为「分档胜率 − 基线胜率」（小数，×100 为 pp）。
    """
    sub = frame[[value_col, ret_col]].dropna()
    if sub.empty:
        return pd.DataFrame(
            columns=["label", "n", "win_rate", "avg_return", "excess_win_rate", "excess_return"]
        )
    base = _base(frame, ret_col, baseline)
    base_ret = float(frame[ret_col].dropna().mean()) if frame[ret_col].notna().any() else 0.0

    sub = sub.copy()
    sub["_bin"] = pd.cut(sub[value_col], bins=bins, labels=labels)
    g = (
        sub.groupby("_bin", observed=True)
        .agg(n=(ret_col, "size"), win_rate=(ret_col, _win_rate), avg_return=(ret_col, "mean"))
        .reset_index()
    )
    g = g.rename(columns={"_bin": "label"})
    g["excess_win_rate"] = g["win_rate"] - base
    g["excess_return"] = g["avg_return"] - base_ret
    return g


def excess_boolean(
    frame: pd.DataFrame,
    mask: pd.Series | np.ndarray,
    label: str,
    ret_col: str = "ret",
    baseline: float | None = None,
) -> dict:
    """单个布尔因子的超额（True 子集 vs 基线）。

    Returns:
        dict：label / n / win_rate / avg_return / excess_win_rate / excess_return。
    """
    mask = pd.Series(np.asarray(mask, dtype=bool), index=frame.index)
    sub = frame.loc[mask, ret_col].dropna()
    base = _base(frame, ret_col, baseline)
    base_ret = float(frame[ret_col].dropna().mean()) if frame[ret_col].notna().any() else 0.0
    win = _win_rate(sub)
    avg = float(sub.mean()) if len(sub) else 0.0
    return {
        "label": label,
        "n": int(len(sub)),
        "win_rate": win,
        "avg_return": avg,
        "excess_win_rate": win - base,
        "excess_return": avg - base_ret,
    }


def cross_excess(
    frame: pd.DataFrame,
    row_col: str,
    row_bins: list[float],
    row_labels: list[str],
    col_col: str,
    col_bins: list[float],
    col_labels: list[str],
    ret_col: str = "ret",
    baseline: float | None = None,
) -> pd.DataFrame:
    """两个数值因子的交叉超额矩阵。

    Returns:
        长表 DataFrame，列：row / col / n / win_rate / excess_win_rate，
        一行 = 一个 (row 档 × col 档) 单元格。
    """
    sub = frame[[row_col, col_col, ret_col]].dropna()
    if sub.empty:
        return pd.DataFrame(columns=["row", "col", "n", "win_rate", "excess_win_rate"])
    base = _base(frame, ret_col, baseline)
    sub = sub.copy()
    sub["_row"] = pd.cut(sub[row_col], bins=row_bins, labels=row_labels)
    sub["_col"] = pd.cut(sub[col_col], bins=col_bins, labels=col_labels)
    g = (
        sub.groupby(["_row", "_col"], observed=True)
        .agg(n=(ret_col, "size"), win_rate=(ret_col, _win_rate))
        .reset_index()
    )
    g = g.rename(columns={"_row": "row", "_col": "col"})
    g["excess_win_rate"] = g["win_rate"] - base
    return g
