"""ETF 连续吸筹策略（跌幅 25%-40% + 底背离）。

逻辑（TOOLS.md「ETF 入场监控规则」）：

    - 回撤：相对近 60 日最高价，跌幅落在 25% ~ 40% 区间（跌太少没性价比，
      跌太多可能基本面破位）。
    - 底背离：价格创近 20 日新低，但 MACD 的 DIF 或 RSI 未同步创新低，
      说明下跌动能衰竭、有资金承接（「吸筹」的 K 线语言）。

统一接口 ``scan(candles, as_of, config) -> list[Signal]``。
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from indicators.macd import calc_macd
from indicators.rsi import calc_rsi
from strategies.etf_accumulation.config import EtfAccumulationConfig, default_config
from strategies.filters import SymbolKind
from strategies.signal import Signal

NAME = "etf_accumulation"
LABEL = "ETF抄底"
DESCRIPTION = "ETF 跌幅 25%-40% + 底背离（MACD/RSI 未创新低）"
SIGNAL_TYPE = "etf_accumulation"
TARGET_KINDS = (SymbolKind.ETF,)


def scan(
    candles: dict[str, pd.DataFrame],
    as_of: date,
    config: EtfAccumulationConfig | None = None,
) -> list[Signal]:
    """对一批 ETF 日线扫描连续吸筹信号。"""
    cfg = config or default_config()
    signals: list[Signal] = []

    for symbol in sorted(candles):
        df = candles[symbol]
        signal = _evaluate(symbol, df, as_of, cfg)
        if signal is not None:
            signals.append(signal)

    return signals


def _evaluate(
    symbol: str, df: pd.DataFrame, as_of: date, cfg: EtfAccumulationConfig
) -> Signal | None:
    """对单只 ETF 判定吸筹信号。不满足条件返回 None。"""
    if df is None or len(df) < cfg.min_bars:
        return None

    closes = df["close"].astype(float).tolist()

    high60 = max(closes[-cfg.drawdown_window :])
    close_now = closes[-1]
    if high60 <= 0:
        return None

    drawdown = (close_now - high60) / high60 * 100.0  # 负数表示回撤

    # 回撤幅度落在 [drawdown_min, drawdown_max]
    if not (-cfg.drawdown_max <= drawdown <= -cfg.drawdown_min):
        return None

    dif, _, _ = calc_macd(closes)
    rsi = calc_rsi(closes)

    window = closes[-cfg.divergence_window :]
    dif_window = dif[-cfg.divergence_window :]
    rsi_window = rsi[-cfg.divergence_window :]

    # 价格创近窗口新低
    price_new_low = close_now <= min(window)

    # 底背离：价格新低，但 DIF / RSI 未创新低
    macd_div = price_new_low and dif[-1] > min(dif_window)
    rsi_div = price_new_low and rsi[-1] > min(rsi_window)

    if not (macd_div or rsi_div):
        return None

    score = 70.0 + (10.0 if macd_div else 0.0) + (10.0 if rsi_div else 0.0)

    return Signal(
        symbol=symbol,
        strategy=NAME,
        signal_type=SIGNAL_TYPE,
        score=score,
        triggered_at=as_of,
        metrics={
            "drawdown_pct": round(drawdown, 2),
            "macd_divergence": macd_div,
            "rsi_divergence": rsi_div,
            "dif_now": round(float(dif[-1]), 4),
            "rsi_now": round(float(rsi[-1]), 2),
            "high60": round(high60, 2),
            "close": round(close_now, 2),
        },
    )
