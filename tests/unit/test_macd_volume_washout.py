"""MACD 水下多头 + 极缩量（washout）策略单元测试。"""

from __future__ import annotations

from datetime import date

from strategies.macd_volume_washout.config import MacdVolumeWashoutConfig
from strategies.macd_volume_washout.strategy import evaluate, scan
from tests.helpers import make_candle_df

AS_OF = date(2026, 8, 27)


def _washout_candles() -> dict:
    """构造 washout 形态：长期阴跌（DIF 深负）→ 尾部小反弹（DIF 拐头）→ 极缩量。"""
    n = 130
    closes = [50.0 * (0.985**i) for i in range(n - 10)]
    last = closes[-1]
    closes += [last * (1.004) ** i for i in range(1, 11)]
    vols = [1000.0] * 120 + [200.0] * 10  # 尾部 10 日缩到 20%
    return {"600001": make_candle_df(closes, volume=vols, high_pad=0.01, low_pad=0.01)}


def _rising_candles() -> dict:
    """持续上涨：DIF > 0，非水下。"""
    closes = [10.0 * (1.03**i) for i in range(80)]
    return {"600002": make_candle_df(closes, high_pad=0.01, low_pad=0.01)}


def _no_shrink_candles() -> dict:
    """下跌但量不缩（恒量）：vr60 ≈ 1.0，不满足极缩量。"""
    closes = [50.0 * (0.985**i) for i in range(130)]
    return {"600003": make_candle_df(closes, volume=1000.0, high_pad=0.01, low_pad=0.01)}


def _config(**overrides) -> MacdVolumeWashoutConfig:
    cfg = MacdVolumeWashoutConfig()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def test_washout_fires_signal():
    """阴跌后反弹 + 极缩量 → 触发信号，metrics 记录 dif/dea/vr60。"""
    candles = _washout_candles()
    cfg = _config(min_amount=0.0)  # 关闭流动性过滤（合成数据成交额小）
    sig = evaluate("600001", candles["600001"], AS_OF, cfg)

    assert sig is not None
    assert sig.strategy == "macd_volume_washout"
    assert sig.symbol == "600001"
    assert sig.metrics["dif"] < 0  # 水下
    assert sig.metrics["dif"] > sig.metrics["dea"]  # 多头
    assert sig.metrics["vr60"] < 0.6  # 极缩量


def test_rising_not_underwater():
    """持续上涨（DIF > 0）→ 不触发。"""
    candles = _rising_candles()
    sig = evaluate("600002", candles["600002"], AS_OF, _config(min_amount=0.0))
    assert sig is None


def test_no_shrink_no_signal():
    """量不缩（恒量）→ 不触发。"""
    candles = _no_shrink_candles()
    sig = evaluate("600003", candles["600003"], AS_OF, _config(min_amount=0.0))
    assert sig is None


def test_min_bars_guard():
    candles = _washout_candles()
    sig = evaluate("600001", candles["600001"].iloc[:50], AS_OF, _config(min_amount=0.0))
    assert sig is None


def test_scan_returns_sorted_symbols():
    """scan 遍历 sorted(candles)，输出信号按代码升序。"""
    candles = _washout_candles()
    # 再加一只可触发的标的（复制并改代码）
    candles["600000"] = candles["600001"].copy()
    sigs = scan(candles, AS_OF, _config(min_amount=0.0))
    assert [s.symbol for s in sigs] == sorted(s.symbol for s in sigs)
    assert len(sigs) == 2
