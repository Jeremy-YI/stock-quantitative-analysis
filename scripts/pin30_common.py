"""pin30 单针下30 的口径共享层（阶段 12：任务 1/2/3 复用）。

把 ``strategies.pin30.strategy`` 里散落的指标公式抽成「按全序列向量化」的版本，
供事后打标 / 分桶 / 状态机复用。口径必须与策略模块逐条一致，见
``run_pin30_bucket.py`` 的 ``--validate-days`` 抽样核对。

与策略模块 ``_evaluate`` 的对应关系：
    short      = _stochastic(closes, lows, short_lookback=3)
    long       = _stochastic(closes, lows, long_lookback=20)
    st_raw     = calc_ema(calc_ema(C,10),10)
    lt_raw     = (SMA14 + SMA28 + SMA57 + SMA114) / 4
    trend_long = st_raw > lt_raw 且 C > lt_raw

注意：策略里 ``_stochastic`` 的分母是 ``(hv-lv) + 0.0001``，且 ``hv-lv <= 0`` 时
直接返回 50.0（不参与分母 eps）。这里逐条复刻，不做任何「改进」。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from indicators.macd import calc_ema

# 与 strategy.py 的 _DEN_EPS 一致
DEN_EPS = 0.0001
SHORT_LOOKBACK = 3
LONG_LOOKBACK = 20
ST_PERIOD = 10
LT_PERIODS = (14, 28, 57, 114)


def _sma_series(values: np.ndarray, period: int) -> np.ndarray:
    """简单移动平均（窗口不足用已有数据平均），与策略 ``_sma`` 逐位一致。"""
    csum = np.concatenate(([0.0], np.cumsum(values)))
    i = np.arange(len(values))
    s = np.maximum(0, i - period + 1)
    return (csum[i + 1] - csum[s]) / (i - s + 1)


def _stochastic_series(closes: np.ndarray, lows: np.ndarray, lookback: int) -> np.ndarray:
    """(C - LLV(L,n)) / (HHV(C,n) - LLV(L,n) + eps) * 100 的逐位版本。

    复刻策略 ``_stochastic``：先算 ``den = hv - lv``，``den <= 0`` → 50.0，
    否则 ``(C - lv) / (den + eps) * 100``。滚动窗口用 ``rolling(min_periods=1)``
    等价于策略里的 ``lows[i-lookback+1:i+1]``（前段窗口不足时取已有数据）。
    """
    lv = pd.Series(lows).rolling(lookback, min_periods=1).min().to_numpy(dtype=float)
    hv = pd.Series(closes).rolling(lookback, min_periods=1).max().to_numpy(dtype=float)
    den = hv - lv
    out = np.where(den <= 0, 50.0, (closes - lv) / (den + DEN_EPS) * 100.0)
    return out


def pin30_series(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """对单只标的算全序列指标，返回 numpy 数组 dict（key: short/long/st_raw/lt_raw/trend/close）。"""
    closes = df["close"].astype(float).to_numpy()
    lows = df["low"].astype(float).to_numpy()
    n = len(closes)

    short = _stochastic_series(closes, lows, SHORT_LOOKBACK)
    long_ = _stochastic_series(closes, lows, LONG_LOOKBACK)

    st_raw = np.asarray(calc_ema(calc_ema(closes.tolist(), ST_PERIOD), ST_PERIOD), dtype=float)

    lt_raw = np.zeros(n, dtype=float)
    for p in LT_PERIODS:
        lt_raw += _sma_series(closes, p)
    lt_raw /= float(len(LT_PERIODS))

    trend = (st_raw > lt_raw) & (closes > lt_raw)

    return {
        "close": closes,
        "short": short,
        "long": long_,
        "st_raw": st_raw,
        "lt_raw": lt_raw,
        "trend": trend,
    }


def bucket_of(trend: bool, long_val: float) -> int:
    """把「单针下30」（short<=30）事件按趋势状态 + 长期随机分桶。

    桶 1：趋势多头 + 长期>=80（原始 pin30，上升趋势洗盘）
    桶 2：趋势多头 + 长期 50~80（上升趋势中段回踩）
    桶 3：非趋势多头 + 长期<=55（深水，下跌趋势）
    桶 4：其余（趋势多头但长期<50；非趋势多头但长期>55）
    """
    if trend and long_val >= 80.0:
        return 1
    if trend and 50.0 <= long_val < 80.0:
        return 2
    if (not trend) and long_val <= 55.0:
        return 3
    return 4


BUCKET_NAMES = {
    1: "桶1 趋势多头+长期>=80（原始pin30）",
    2: "桶2 趋势多头+长期50~80（中段回踩）",
    3: "桶3 非趋势多头+长期<=55（深水）",
    4: "桶4 其余",
}
