"""因子数据集构建：从全市场日线预计算指标，产出长表供因子分析。

每一行 = 某标的在某交易日的截面因子值 + 持有 ``hold_days`` 日的前向收益。
指标全部向量化预计算（每标的一次），避免逐日重算；与 /tmp 四个实验脚本同口径。

因子列：
    vr5 / vr20 / vr60      量比（当日量 / 过去 5/20/60 日均量，不含当日）
    dif / dea              MACD 的 DIF / DEA
    above                  MACD 水上（DIF > 0）
    gold                   MACD 多头（DIF > DEA）
    cross                  MACD 当日金叉（DIF 上穿 DEA）
    below_bull             水下多头（DIF < 0 且 DIF > DEA）
    ma5..ma120             收盘价 MA（5/13/25/75/120）
    perfect                完美多头 5>13>25>75>120
    short_bull             短期多头 5>13>25
    above120               站上 MA120
    mid_bull               中期多头 MA25>MA75
    dev5                   偏离度 (close-MA5)/MA5
    ret                    持有 hold_days 日的前向收益（close[i+hold]/close[i]-1）
"""

from __future__ import annotations

import random
from datetime import date

import numpy as np
import pandas as pd

from indicators.macd import calc_macd
from indicators.volume import calc_volume_ratio

# Jeremy 真实均线参数（5/13/25/75/120，与 /tmp/ma_factor.py 一致）
MAS = (5, 13, 25, 75, 120)

# 最长的均线窗口 + MACD 慢线余量：少于该根数不产出截面
_MIN_BARS = 130


def _factor_frame(df: pd.DataFrame) -> pd.DataFrame | None:
    """对单只标的的日线预计算全部因子，返回等长 DataFrame（数据不足返回 None）。"""
    if df is None or len(df) < _MIN_BARS:
        return None

    closes = pd.to_numeric(df["close"], errors="coerce").astype(float)
    volumes = pd.to_numeric(df["volume"], errors="coerce").astype(float)
    n = len(closes)

    out = pd.DataFrame(index=df.index)
    out["close"] = closes

    ma = {p: closes.rolling(p).mean() for p in MAS}
    for p in MAS:
        out[f"ma{p}"] = ma[p]

    out["vr5"] = calc_volume_ratio(volumes.tolist(), period=5)
    out["vr20"] = calc_volume_ratio(volumes.tolist(), period=20)
    out["vr60"] = calc_volume_ratio(volumes.tolist(), period=60)

    dif, dea, bar = calc_macd(closes.tolist())
    out["dif"] = np.asarray(dif, dtype=float)
    out["dea"] = np.asarray(dea, dtype=float)
    out["macd_bar"] = np.asarray(bar, dtype=float)

    dif_arr = out["dif"].to_numpy()
    dea_arr = out["dea"].to_numpy()
    out["above"] = dif_arr > 0.0
    out["gold"] = dif_arr > dea_arr
    # 当日金叉：DIF 上穿 DEA（前一交易日 dif<=dea 且当日 dif>dea）
    cross = np.zeros(n, dtype=bool)
    for i in range(1, n):
        cross[i] = dif_arr[i] > dea_arr[i] and dif_arr[i - 1] <= dea_arr[i - 1]
    out["cross"] = cross
    out["below_bull"] = (dif_arr < 0.0) & (dif_arr > dea_arr)

    ma5 = ma[5].to_numpy()
    ma13 = ma[13].to_numpy()
    ma25 = ma[25].to_numpy()
    ma75 = ma[75].to_numpy()
    ma120 = ma[120].to_numpy()
    close_arr = closes.to_numpy()
    out["perfect"] = (ma5 > ma13) & (ma13 > ma25) & (ma25 > ma75) & (ma75 > ma120)
    out["short_bull"] = (ma5 > ma13) & (ma13 > ma25)
    out["above120"] = close_arr > ma120
    out["mid_bull"] = ma25 > ma75
    out["dev5"] = (close_arr - ma5) / ma5

    return out


def build_factor_dataset(
    candles: dict[str, pd.DataFrame],
    start: date,
    end: date,
    hold_days: int = 5,
    min_bars: int = _MIN_BARS,
    sample: int | None = None,
    seed: int = 7,
) -> pd.DataFrame:
    """从全市场日线构建因子长表。

    Args:
        candles: {6 位代码: 日线 DataFrame}。
        start/end: 截面日期区间（含两端）。
        hold_days: 前向收益持有期（交易日）。
        min_bars: 单标的最少历史根数。
        sample: 抽样标的数（None = 全量），用于快速探索。
        seed: 抽样随机种子。

    Returns:
        长表 DataFrame，列见模块 docstring；``ret`` 为 close[i+hold]/close[i]-1，
        数据末尾不足 hold_days 的行被剔除。
    """
    symbols = list(candles.keys())
    if sample is not None and sample < len(symbols):
        random.Random(seed).shuffle(symbols)
        symbols = symbols[:sample]

    frames: list[pd.DataFrame] = []
    for symbol in symbols:
        df = candles.get(symbol)
        if df is None or len(df) < min_bars:
            continue
        feats = _factor_frame(df.reset_index(drop=True))
        if feats is None:
            continue
        feats = feats.reset_index(drop=True)
        # 前向收益（用收盘价索引，天然处理停牌前向跳）
        closes = feats["close"].to_numpy()
        n = len(closes)
        ret = np.full(n, np.nan)
        for i in range(n - hold_days):
            ret[i] = closes[i + hold_days] / closes[i] - 1.0
        feats["ret"] = ret

        dcol = "date" if "date" in df.columns else df.columns[0]
        feats["date"] = pd.to_datetime(df[dcol]).dt.date.tolist()
        feats["symbol"] = symbol
        frames.append(feats)

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    out = out[(out["date"] >= start) & (out["date"] <= end)]
    out = out[out["ret"].notna()]
    return out.reset_index(drop=True)
