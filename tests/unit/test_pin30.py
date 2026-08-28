"""单针下30（PIN30）策略单元测试。"""

from __future__ import annotations

from datetime import date

from strategies.pin30 import scan
from tests.helpers import make_candle_df

AS_OF = date(2026, 1, 1)


def _signal_types(signals) -> set[str]:
    return {s.signal_type for s in signals}


def test_pin30_triggers_on_pullback_in_uptrend():
    """长期上涨后单日回踩 → 短期≤30 且 长期≥80 → 触发 pin30。"""
    rise = [100 * (1.01 ** i) for i in range(127)]
    closes = rise + [rise[-1] * 1.015, rise[-1] * 0.985]
    df = make_candle_df(closes, high_pad=0.005, low_pad=0.005)
    assert "pin30" in _signal_types(scan({"600001": df}, AS_OF))


def test_b1w_triggers_on_decline():
    """持续下跌 → J<16 → 触发 b1_w。"""
    closes = [100 * (0.98 ** i) for i in range(130)]
    df = make_candle_df(closes, high_pad=0.01, low_pad=0.01)
    assert "b1_w" in _signal_types(scan({"600001": df}, AS_OF))


def test_no_signal_on_steady_rise():
    """稳步上涨（无回踩）→ 无信号。"""
    closes = [100 * (1.01 ** i) for i in range(130)]
    df = make_candle_df(closes, high_pad=0.005, low_pad=0.005)
    assert scan({"600001": df}, AS_OF) == []


def test_insufficient_bars():
    """少于 min_bars(120) → 无信号。"""
    closes = [100 * (1.01 ** i) for i in range(50)]
    assert scan({"600001": make_candle_df(closes)}, AS_OF) == []


def test_empty_candles():
    assert scan({}, AS_OF) == []
