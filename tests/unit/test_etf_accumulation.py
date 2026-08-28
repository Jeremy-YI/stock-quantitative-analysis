"""ETF 连续吸筹策略单元测试。"""

from __future__ import annotations

from datetime import date

from strategies.etf_accumulation import scan
from tests.helpers import make_candle_df

AS_OF = date(2026, 8, 27)


def _drawdown_then_flatten() -> dict:
    """跌幅 -35% + MACD 底背离的合成 ETF K 线。"""
    closes = []
    for i in range(40):
        closes.append(100 - i * (30 / 40))
    base = closes[-1]
    for i in range(20):
        closes.append(base - i * 0.3)
    return {"588710": make_candle_df(closes, high_pad=0.01, low_pad=0.01)}


def test_triggers_on_drawdown_and_divergence():
    sigs = scan(_drawdown_then_flatten(), AS_OF)
    assert [s.signal_type for s in sigs] == ["etf_accumulation"]
    assert sigs[0].metrics["macd_divergence"] is True


def test_no_signal_when_drawdown_too_shallow():
    """跌幅不足 25% → 不触发。"""
    closes = [100 - i * 0.15 for i in range(60)]  # -9% 回撤
    df = make_candle_df(closes, high_pad=0.01, low_pad=0.01)
    assert scan({"588710": df}, AS_OF) == []


def test_no_signal_when_drawdown_too_deep():
    """跌幅超过 40% → 视为趋势破位，不触发。"""
    closes = [100 - i * 1.0 for i in range(60)]  # -59% 回撤
    df = make_candle_df(closes, high_pad=0.01, low_pad=0.01)
    assert scan({"588710": df}, AS_OF) == []


def test_no_signal_without_divergence():
    """匀速单边下跌（无 MACD 底背离）→ 不触发。"""
    closes = [100 - i * (30 / 60) for i in range(60)]  # 匀速跌 30%
    df = make_candle_df(closes, high_pad=0.01, low_pad=0.01)
    assert scan({"588710": df}, AS_OF) == []


def test_insufficient_bars():
    assert scan({"588710": make_candle_df([10.0] * 30)}, AS_OF) == []


def test_empty_candles():
    assert scan({}, AS_OF) == []
