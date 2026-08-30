"""MACD 水下多头 + 极缩量（washout）策略：DIF<0 且 DIF>DEA 且 vr60<0.6。

实测依据见 config.py 与 docs/因子研究报告.md：这是「MACD 状态 × 量能」交叉
矩阵里最强的组合（持有 5 日超额 +9.39pp），赌超卖后的均值回归反弹。属于
「均值回归 / 埋伏型」选股，与偷涨（stealth_rally）同为水下逻辑，但用「60 日
量比极缩」代替「二次金叉 + 红柱」作为右侧确认。

信号口径与 /tmp/macd_vol_cross.py 完全一致：
    - 水下：DIF < 0（MACD 长周期仍空头）
    - 多头：DIF > DEA（短周期已拐头向上，抛压衰竭）
    - 极缩量：当日成交量 / 过去 60 日平均成交量 < 0.6
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from indicators.macd import calc_macd
from indicators.volume import calc_volume_ratio
from strategies.filters import SymbolKind
from strategies.macd_volume_washout.config import (
    MacdVolumeWashoutConfig,
    default_config,
)
from strategies.signal import Signal

NAME = "macd_volume_washout"
LABEL = "缩量洗盘"
DESCRIPTION = "MACD 水下多头（DIF<0 且 DIF>DEA）+ 60日量比 <0.6（极缩量洗盘）"
SIGNAL_TYPE = "washout"
TARGET_KINDS = (SymbolKind.STOCK,)


def evaluate(
    symbol: str, df: pd.DataFrame, as_of: date, cfg: MacdVolumeWashoutConfig
) -> Signal | None:
    """对单只标的判定 washout 信号。不满足返回 None。"""
    if df is None or len(df) < cfg.min_bars:
        return None

    closes = df["close"].astype(float).tolist()
    volumes = df["volume"].astype(float).tolist()
    n = len(closes)

    dif, dea, _bar = calc_macd(closes)
    dif_now = float(dif[-1])
    dea_now = float(dea[-1])

    # 水下多头：DIF < 0 且 DIF > DEA
    if not (dif_now < 0 and dif_now > dea_now):
        return None

    # 极缩量：当日量 / 过去 60 日均量 < 0.6
    ratio = calc_volume_ratio(volumes, period=cfg.volume_ratio_window)
    vr = float(ratio[-1])
    if vr >= cfg.volume_ratio_max:
        return None

    # 流动性：近 20 日均成交额下限
    amounts = df["amount"].astype(float).tolist()
    window = amounts[-20:] if len(amounts) >= 20 else amounts
    avg_amount = sum(window) / len(window) if window else 0.0
    if avg_amount < cfg.min_amount:
        return None

    # score：越缩量分越高（供组合回测策略内排序取前 N）
    score = round(cfg.volume_ratio_max - vr, 4)

    return Signal(
        symbol=symbol,
        strategy=NAME,
        signal_type=SIGNAL_TYPE,
        score=score,
        triggered_at=as_of,
        metrics={
            "dif": round(dif_now, 4),
            "dea": round(dea_now, 4),
            "vr60": round(vr, 4),
            "avg_amount_20d": round(avg_amount, 0),
            "close": round(float(closes[-1]), 2),
        },
    )


def scan(
    candles: dict[str, pd.DataFrame],
    as_of: date,
    config: MacdVolumeWashoutConfig | None = None,
) -> list[Signal]:
    """对一批日线扫描 washout 信号。"""
    cfg = config or default_config()
    signals: list[Signal] = []
    for symbol in sorted(candles):
        sig = evaluate(symbol, candles[symbol], as_of, cfg)
        if sig is not None:
            signals.append(sig)
    return signals
