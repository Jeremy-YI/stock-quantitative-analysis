"""MACD 指标模块。"""

from indicators.macd.macd import (
    BAR_MULTIPLIER,
    FAST_PERIOD,
    MIN_BARS_FOR_MACD,
    SIGNAL_PERIOD,
    SLOW_PERIOD,
    MacdResult,
    calc_ema,
    calc_macd,
)

__all__ = [
    "BAR_MULTIPLIER",
    "FAST_PERIOD",
    "MIN_BARS_FOR_MACD",
    "SIGNAL_PERIOD",
    "SLOW_PERIOD",
    "MacdResult",
    "calc_ema",
    "calc_macd",
]
