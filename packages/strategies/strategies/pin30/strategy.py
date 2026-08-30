"""单针下30（PIN30，moomoo 随机指标口径）+ B1_W 超卖策略。

两个信号子类型：

    pin30 = 趋势多头 + 短期随机 <= 30 + 长期随机 >= 80（回调到位）
    b1_w  = J < 16（KDJ 超卖）

短期 / 长期随机指标、趋势多头的公式复刻 `us_pin30_watchlist.py::calc_pin30`，
详见 docs/策略迁移说明.md（TOOLS.md 的「K≤30 且 D≥80」在此按随机指标口径落地）。
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from indicators.kdj import calc_kdj
from indicators.macd import calc_ema
from strategies.filters import SymbolKind
from strategies.pin30.config import Pin30Config, default_config
from strategies.signal import Signal

NAME = "pin30"
LABEL = "单针"
DESCRIPTION = "单针下30（moomoo 随机指标口径）+ B1_W 超卖（J<16）"
TARGET_KINDS = (SymbolKind.STOCK,)

SCORE = {"pin30": 75.0, "b1_w": 70.0}

# 随机指标分母防零（与旧脚本 us_pin30_watchlist 的 +0.0001 一致）
_DEN_EPS = 0.0001


def scan(
    candles: dict[str, pd.DataFrame],
    as_of: date,
    config: Pin30Config | None = None,
) -> list[Signal]:
    """对一批日线扫描单针下30 / B1_W 信号。"""
    cfg = config or default_config()
    signals: list[Signal] = []

    for symbol in sorted(candles):
        df = candles[symbol]
        signals.extend(_evaluate(symbol, df, as_of, cfg))

    return signals


def _evaluate(
    symbol: str, df: pd.DataFrame, as_of: date, cfg: Pin30Config
) -> list[Signal]:
    """对单只标的判定。数据不足返回空列表。"""
    if df is None or len(df) < cfg.min_bars:
        return []

    closes = df["close"].astype(float).tolist()
    highs = df["high"].astype(float).tolist()
    lows = df["low"].astype(float).tolist()

    close_now = closes[-1]

    # 趋势多头：ST_RAW > LT_RAW 且 C > LT_RAW
    st_raw = calc_ema(calc_ema(closes, cfg.st_period), cfg.st_period)[-1]
    lt_raw = _lt_raw(closes, cfg.lt_periods)
    trend_long = st_raw > lt_raw and close_now > lt_raw

    # 短期 / 长期随机位置
    short_val = _stochastic(closes, lows, cfg.short_lookback)
    long_val = _stochastic(closes, lows, cfg.long_lookback)

    out: list[Signal] = []

    if trend_long and short_val <= cfg.short_threshold and long_val >= cfg.long_threshold:
        out.append(
            Signal(
                symbol=symbol,
                strategy=NAME,
                signal_type="pin30",
                score=SCORE["pin30"],
                triggered_at=as_of,
                metrics={
                    "short": round(short_val, 4),
                    "long": round(long_val, 4),
                    "st_raw": round(st_raw, 4),
                    "lt_raw": round(lt_raw, 4),
                    "close": round(close_now, 4),
                },
            )
        )

    # B1_W 超卖：J < 16
    k_vals, d_vals, j_vals = calc_kdj(highs, lows, closes)
    j_now = j_vals[-1]
    if j_now < cfg.j_b1w_threshold:
        out.append(
            Signal(
                symbol=symbol,
                strategy=NAME,
                signal_type="b1_w",
                score=SCORE["b1_w"],
                triggered_at=as_of,
                metrics={
                    "j": round(j_now, 4),
                    "k": round(k_vals[-1], 4),
                    "d": round(d_vals[-1], 4),
                    "short": round(short_val, 4),
                    "long": round(long_val, 4),
                    "close": round(close_now, 4),
                },
            )
        )

    return out


def _sma(values: list[float], period: int) -> list[float]:
    """简单移动平均（窗口不足用已有数据平均），与旧脚本 sma 一致。"""
    result: list[float] = []
    for i in range(len(values)):
        s = max(0, i - period + 1)
        result.append(sum(values[s : i + 1]) / (i - s + 1))
    return result


def _lt_raw(closes: list[float], periods: tuple[int, ...]) -> float:
    """LT_RAW = 四条均线的平均（取最后一根）。"""
    total = 0.0
    for p in periods:
        total += _sma(closes, p)[-1]
    return total / len(periods)


def _stochastic(closes: list[float], lows: list[float], lookback: int) -> float:
    """(C - LLV(L,n)) / (HHV(C,n) - LLV(L,n)) * 100，只算最后一根。"""
    i = len(closes) - 1
    lv = min(lows[i - lookback + 1 : i + 1])
    hv = max(closes[i - lookback + 1 : i + 1])
    den = hv - lv
    if den <= 0:
        return 50.0
    return (closes[i] - lv) / (den + _DEN_EPS) * 100.0
