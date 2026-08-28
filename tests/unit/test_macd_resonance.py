"""MACD 月周共振策略单元测试：边界与守卫。"""

from __future__ import annotations

from datetime import date

from strategies.macd_resonance import scan
from tests.helpers import make_candle_df

AS_OF = date(2026, 1, 1)


def test_empty_candles():
    assert scan({}, AS_OF) == []


def test_insufficient_daily_bars():
    # 少于 min_daily_bars(150) 直接跳过
    candles = {"600001": make_candle_df([100 * (1.01 ** i) for i in range(100)])}
    assert scan(candles, AS_OF) == []


def test_long_steady_rise_has_no_underwater_cross():
    """长期上涨（月线水上）但周线无水下金叉 → 不触发。"""
    closes = [100 * (1.005 ** i) for i in range(900)]
    candles = {"600001": make_candle_df(closes, high_pad=0.002, low_pad=0.002)}
    assert scan(candles, AS_OF) == []


def test_long_decline_has_no_signal():
    """长期下跌（月线水下）→ 不触发。"""
    closes = [100 * (0.995 ** i) for i in range(900)]
    candles = {"600001": make_candle_df(closes, high_pad=0.002, low_pad=0.002)}
    assert scan(candles, AS_OF) == []
