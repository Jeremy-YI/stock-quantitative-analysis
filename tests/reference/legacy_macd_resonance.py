"""旧脚本参考实现：MACD 月线水上 + 周线底部金叉（仅用于一致性测试，不进生产代码）。

从 `~/.openclaw/workspace/tools/macd_monthly_water_weekly_goldencross.py`
原样抽取的 ``macd`` / ``resample_ohlc`` / ``analyze`` 逻辑，只是把
``analyze`` 的入参从「文件路径」改成「已加载的日线 DataFrame」，方便与
新实现 `strategies.macd_resonance` 用同一份 candles 比对。

请勿在业务代码中 import 本模块。
"""

from __future__ import annotations

import pandas as pd


def legacy_macd(close: pd.Series):
    """旧脚本的 MACD（pandas ewm，adjust=False，首值做种子）。"""
    ef = close.ewm(span=12, adjust=False).mean()
    es = close.ewm(span=26, adjust=False).mean()
    dif = ef - es
    dea = dif.ewm(span=9, adjust=False).mean()
    hist = 2 * (dif - dea)
    return dif, dea, hist


def legacy_resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """旧脚本的 resample_ohlc（周线 W-FRI / 月线 ME）。"""
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.set_index("date")
    return d.resample(rule).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()


def legacy_analyze(code: str, df: pd.DataFrame):
    """旧脚本 analyze 的等价实现（入参改为日线 DataFrame）。

    返回命中 dict 或 None，字段与旧脚本一致。
    """
    if df is None or len(df) < 150:
        return None
    try:
        m = legacy_resample_ohlc(df, "ME")
        w = legacy_resample_ohlc(df, "W-FRI")
    except Exception:
        return None
    if len(m) < 30 or len(w) < 60:
        return None

    mdif, mdea, _ = legacy_macd(m["close"])
    wdif, wdea, _ = legacy_macd(w["close"])

    m_dif_now = float(mdif.iloc[-1])
    m_dea_now = float(mdea.iloc[-1])

    if m_dif_now <= 0:
        return None

    cross_week = None
    cross_dif = None
    wdif_arr = wdif.values
    wdea_arr = wdea.values
    for i in range(len(wdif_arr) - 1, max(len(wdif_arr) - 7, 0), -1):
        if wdif_arr[i - 1] <= wdea_arr[i - 1] and wdif_arr[i] > wdea_arr[i]:
            cross_week = w.index[i]
            cross_dif = float(wdif_arr[i])
            break

    if cross_week is None:
        return None
    if cross_dif >= 0:
        return None

    return {
        "symbol": code,
        "m_dif": round(m_dif_now, 3),
        "m_dea": round(m_dea_now, 3),
        "w_dif_now": round(float(wdif.iloc[-1]), 3),
        "w_dea_now": round(float(wdea.iloc[-1]), 3),
        "cross_week": str(cross_week.date()),
        "cross_dif": round(cross_dif, 3),
        "close": round(float(df["close"].iloc[-1]), 2),
    }
