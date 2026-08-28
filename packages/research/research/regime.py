"""regime 分层分析：按市场环境分档，对比「趋势跟随 / 均值回归」组合超额。

趋势跟随组合（TF）与均值回归组合（MR）定义（与 /tmp/regime_test.py 一致）：
    TF = 水上多头（DIF>0 且 DIF>DEA）& 完美多头（5>13>25>75>120）& 站上 MA120
    MR = 水下多头（DIF<0 且 DIF>DEA）& vr60 < 0.6
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _win_rate(series: pd.Series) -> float:
    if len(series) == 0:
        return 0.0
    return float((series > 0).mean())


def layered_excess(
    frame: pd.DataFrame,
    regime_col: str,
    regime_bins: list[float],
    regime_labels: list[str],
    trend_mask: pd.Series | np.ndarray,
    reversion_mask: pd.Series | np.ndarray,
    ret_col: str = "ret",
) -> pd.DataFrame:
    """按 regime 分档，输出区间基线胜率 + 趋势跟随 / 均值回归组合的超额。

    Args:
        frame: 因子长表（含 regime_col 与 ret_col）。
        regime_col: 市场环境指标列名（如 r20 / activity / drawdown）。
        regime_bins / regime_labels: 分箱。
        trend_mask / reversion_mask: 两个组合的布尔 mask（与 frame 等长）。
        ret_col: 收益列名。

    Returns:
        DataFrame，列：label / baseline_win_rate / trend_n / trend_excess /
        reversion_n / reversion_excess。excess 为「组合胜率 − 区间基线胜率」
        （小数，×100 为 pp）；样本不足（< min_n）记 NaN。
    """
    trend = pd.Series(np.asarray(trend_mask, dtype=bool), index=frame.index)
    reversion = pd.Series(np.asarray(reversion_mask, dtype=bool), index=frame.index)

    sub = frame[[regime_col, ret_col]].copy()
    sub["_bin"] = pd.cut(sub[regime_col], bins=regime_bins, labels=regime_labels)

    rows: list[dict] = []
    for label in regime_labels:
        sel = sub["_bin"] == label
        base = _win_rate(frame.loc[sel.values, ret_col].dropna())
        t = frame.loc[sel.values & trend.values, ret_col].dropna()
        r = frame.loc[sel.values & reversion.values, ret_col].dropna()
        rows.append(
            {
                "label": label,
                "baseline_win_rate": base,
                "trend_n": int(len(t)),
                "trend_excess": (_win_rate(t) - base) if len(t) >= 150 else np.nan,
                "reversion_n": int(len(r)),
                "reversion_excess": (_win_rate(r) - base) if len(r) >= 150 else np.nan,
            }
        )
    return pd.DataFrame(rows)
