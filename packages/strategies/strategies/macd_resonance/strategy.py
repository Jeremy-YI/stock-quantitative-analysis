"""MACD 月线水上 + 周线底部金叉（月周共振）策略。

逻辑（Jeremy 2026-08-19 定，复刻 `macd_monthly_water_weekly_goldencross.py`）：

    - 月线 MACD 在水上（月线 DIF > 0）：长周期多头，定方向。
    - 周线 MACD 最近 6 周内出现底部金叉（DIF 上穿 DEA，且金叉当周 DIF < 0）：
      中期转强。

一旦周线 MACD 上水，日线进入主升段。score 取月线 DIF（越大越强，与旧脚本排序一致）。
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from indicators.macd import calc_macd
from market.resample import resample_monthly, resample_weekly
from strategies.filters import SymbolKind
from strategies.macd_resonance.config import MacdResonanceConfig, default_config
from strategies.signal import Signal

NAME = "macd_resonance"
DESCRIPTION = "月线 MACD 水上 + 周线 MACD 底部金叉（月周共振）"
SIGNAL_TYPE = "macd_resonance"
TARGET_KINDS = (SymbolKind.STOCK,)


def scan(
    candles: dict[str, pd.DataFrame],
    as_of: date,
    config: MacdResonanceConfig | None = None,
) -> list[Signal]:
    """对一批日线扫描月周 MACD 共振信号。"""
    cfg = config or default_config()
    signals: list[Signal] = []

    for symbol in sorted(candles):
        df = candles[symbol]
        signal = _evaluate(symbol, df, as_of, cfg)
        if signal is not None:
            signals.append(signal)

    return signals


def _evaluate(
    symbol: str, df: pd.DataFrame, as_of: date, cfg: MacdResonanceConfig
) -> Signal | None:
    """对单只标的判定月周共振。不满足任一条件返回 None。"""
    if df is None or len(df) < cfg.min_daily_bars:
        return None

    try:
        monthly = resample_monthly(df)
        weekly = resample_weekly(df)
    except Exception:
        return None

    if len(monthly) < cfg.min_monthly_bars or len(weekly) < cfg.min_weekly_bars:
        return None

    m_dif, m_dea, _ = calc_macd(monthly["close"].astype(float).tolist())
    w_dif, w_dea, _ = calc_macd(weekly["close"].astype(float).tolist())

    m_dif_now = float(m_dif[-1])
    m_dea_now = float(m_dea[-1])

    # 月线水上：DIF > 0
    if m_dif_now <= cfg.monthly_dif_above:
        return None

    # 周线底部金叉：最近 N 周内 DIF 上穿 DEA，且金叉当周 DIF < 0
    cross_week = None
    cross_dif = None
    n = len(w_dif)
    stop = max(n - 1 - cfg.cross_lookback_weeks, 0)
    for i in range(n - 1, stop, -1):
        if w_dif[i - 1] <= w_dea[i - 1] and w_dif[i] > w_dea[i]:
            cross_week = weekly.index[i]
            cross_dif = float(w_dif[i])
            break

    if cross_week is None:
        return None
    if cross_dif >= cfg.cross_dif_below:
        return None

    return Signal(
        symbol=symbol,
        strategy=NAME,
        signal_type=SIGNAL_TYPE,
        score=round(m_dif_now, 3),
        triggered_at=as_of,
        metrics={
            "m_dif": round(m_dif_now, 4),
            "m_dea": round(m_dea_now, 4),
            "w_dif_now": round(float(w_dif[-1]), 4),
            "w_dea_now": round(float(w_dea[-1]), 4),
            "cross_dif": round(cross_dif, 4),
            "cross_week": str(cross_week.date()),
            "close": round(float(df["close"].iloc[-1]), 4),
        },
    )
