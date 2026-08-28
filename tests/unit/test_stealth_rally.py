"""偷涨型策略单元测试。"""

from __future__ import annotations

from datetime import date

from strategies.stealth_rally import scan
from strategies.stealth_rally.strategy import _has_recent_limit_up
from tests.helpers import make_candle_df

AS_OF = date(2026, 1, 1)


def test_has_recent_limit_up_detects_10pct():
    """修正版涨停过滤：真实昨收口径，+10% 大阳应被识别为涨停。"""
    closes = [10.0] * 5 + [11.0]  # 最后一天 +10%
    assert _has_recent_limit_up(closes, lookback=10, pct_threshold=9.5) is True


def test_has_recent_limit_up_ignores_small_gains():
    closes = [10.0] * 5 + [10.5]  # +5% 不构成涨停
    assert _has_recent_limit_up(closes, lookback=10, pct_threshold=9.5) is False


def test_has_recent_limit_up_outside_lookback():
    """涨停发生在回看窗口之外 → 不算。"""
    closes = [10.0, 11.0] + [10.0] * 12  # 涨停在第 2 天，距今 12 天
    assert _has_recent_limit_up(closes, lookback=10, pct_threshold=9.5) is False


def test_empty_candles():
    assert scan({}, AS_OF) == []


def test_insufficient_bars():
    closes = [100 * (1.01 ** i) for i in range(30)]  # 少于 min_bars(60)
    assert scan({"600001": make_candle_df(closes)}, AS_OF) == []


def test_steady_rise_no_signal():
    """长期上涨（无水下二次金叉形态）→ 无信号。"""
    closes = [100 * (1.005 ** i) for i in range(120)]
    assert scan({"600001": make_candle_df(closes)}, AS_OF) == []
