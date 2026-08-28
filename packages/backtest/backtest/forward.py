"""信号验证模式的前向收益计算（close-to-close，与 top5_verify.py 对齐）。

口径：
    信号在 T 日收盘后触发（策略只看 T 日及以前的 K 线），
    持有 N 个交易日的收益 = close[T+N] / close[T] - 1（收盘对收盘）。

这与 ``top5_verify.py`` 的「次日验证」完全一致：N=1 时的正收益占比就是
旧脚本里的命中率（hit_rate）。停牌天然按「持有跨越停牌」处理——标的数据里
没有停牌日的 K 线，索引式前向直接跳到复牌后的那根，等价于被套住直到复牌。

边界：
    - 信号日不在标的数据里 → 全部收益为 None（标的数据缺失）。
    - 信号日之后不足 N 根（数据末尾）→ 该持有期收益为 None，统计时剔除。
"""

from __future__ import annotations

from datetime import date

import pandas as pd


def forward_returns(
    df: pd.DataFrame,
    signal_date: date,
    hold_days: list[int],
) -> dict[int, float | None]:
    """计算信号日之后各持有期的收盘对收盘收益。

    Args:
        df: 标的全量日线（按日期升序，含 date/close 列）。
        signal_date: 信号触发日（须等于 df 里某根 K 线的日期）。
        hold_days: 持有期（交易日）列表。

    Returns:
        {hold_days: 收益率或 None}。None 表示数据不足（信号日缺失 / 末尾不足）。
    """
    out: dict[int, float | None] = {n: None for n in hold_days}
    if df is None or df.empty:
        return out

    # 用日期定位信号日索引（df 已按日期升序）
    dates = df["date"].tolist()
    closes = df["close"].astype(float).tolist()

    try:
        idx = dates.index(signal_date)
    except ValueError:
        return out

    base_close = closes[idx]
    if base_close <= 0:
        return out

    for n in hold_days:
        j = idx + n
        if j >= len(closes):
            continue
        out[n] = closes[j] / base_close - 1.0

    return out


def forward_return_series(
    df: pd.DataFrame,
    signal_date: date,
    hold_days: int,
) -> float | None:
    """单持有期的前向收益（便捷函数）。"""
    return forward_returns(df, signal_date, [hold_days])[hold_days]
