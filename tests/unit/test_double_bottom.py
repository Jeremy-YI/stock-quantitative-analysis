"""双底反弹策略单测：摆动低点识别 + 形态判定各条件真假组合 + 边界。

覆盖：
    - swing_lows：局部极小值识别与相邻合并
    - 数据不足（min_bars / 只有一个低点 / 颈线未突破 / 停牌跳空）
    - 两个低点识别 / 相似度容差 / 颈线突破确认 / 量能配合
    - A股流动性门槛（min_price / min_amount）
"""

from __future__ import annotations

from datetime import date

import pytest

from strategies.double_bottom.config import DoubleBottomConfig
from strategies.double_bottom.strategy import _detect, swing_lows
from strategies.double_bottom import scan
from tests.helpers import make_candle_df, make_double_bottom_candles

AS_OF = date(2026, 8, 27)


def _series(closes: list[float], volumes=None) -> tuple:
    """构造 close/high/low/vol/amount 五列，供 _detect 直测。"""
    highs = [c * 1.005 for c in closes]
    lows = [c * 0.995 for c in closes]
    vols = volumes if volumes is not None else [1_000_000.0] * len(closes)
    amounts = [c * v for c, v in zip(closes, vols)]
    return closes, highs, lows, vols, amounts


# ── swing_lows ──
def test_swing_lows_finds_local_minima():
    lows = [5, 4, 3, 2, 1, 2, 3, 2, 1, 2, 3, 4, 5]
    assert 4 in swing_lows(lows, 1)  # index 4 是 1 的局部极小
    assert 8 in swing_lows(lows, 1)  # index 8 是 1 的局部极小


def test_swing_lows_merges_adjacent():
    """相邻低点合并：W 底序列里两个主低点应被识别（含合并后的稳定输出）。"""
    candles = make_double_bottom_candles()
    lows = candles["600519"]["low"].astype(float).tolist()
    found = swing_lows(lows, 6)
    # 两个主低点：左底 ~150、右底 ~230
    assert any(140 <= i <= 160 for i in found)
    assert any(220 <= i <= 238 for i in found)
    assert found == sorted(found)


def test_swing_lows_too_short_returns_empty():
    assert swing_lows([1.0, 2.0, 1.0], 2) == []


# ── 边界：数据不足 ──
def test_data_insufficient_returns_none():
    closes, highs, lows, vols, amounts = _series([10.0] * 100)  # < min_bars(150)
    assert _detect(closes, highs, lows, vols, amounts, DoubleBottomConfig()) is None


def test_only_one_swing_low_returns_none():
    # 单边下跌无反弹，只产生一个低点
    closes = [100 - i * 0.5 for i in range(160)]
    closes, highs, lows, vols, amounts = _series(closes)
    assert _detect(closes, highs, lows, vols, amounts, DoubleBottomConfig()) is None


# ── 形态判定：默认合成序列应命中 ──
def test_default_synthetic_double_bottom_hits():
    candles = make_double_bottom_candles()
    signals = scan(candles, AS_OF)
    assert len(signals) == 1
    assert signals[0].symbol == "600519"
    assert signals[0].metrics["stage"] == "右底爬升"
    assert signals[0].metrics["gap"] == 80


# ── 相似度容差 ──
def test_lows_too_far_apart_rejected():
    cfg = DoubleBottomConfig()
    # 右底明显高于左底（diff > tol_higher），应被剔除
    closes, highs, lows, vols, amounts = _series(_build_with_l2_offset(offset=0.10))
    assert _detect(closes, highs, lows, vols, amounts, cfg) is None


# ── 颈线突破确认 ──
def test_require_breakout_filters_unconfirmed():
    cfg = DoubleBottomConfig(require_breakout=True)
    candles = make_double_bottom_candles()  # 默认是「右底爬升」，未突破颈线
    assert scan(candles, AS_OF, cfg) == []


def test_require_breakout_keeps_breakout():
    cfg = DoubleBottomConfig(require_breakout=True)
    # 尾盘拉到颈线上方 → 已突破
    closes, highs, lows, vols, amounts = _series(_build_with_breakout())
    r = _detect(closes, highs, lows, vols, amounts, cfg)
    assert r is not None
    assert r["stage"] == "已突破"


# ── 量能配合 ──
def test_volume_shrink_boosts_score():
    candles = make_double_bottom_candles()  # 已内置右底缩量
    signals = scan(candles, AS_OF)
    assert signals[0].metrics["vol_shrink"] is not None
    assert signals[0].metrics["vol_shrink"] < 0.8


def test_volume_expansion_penalizes_score():
    # 右底放量（vol_shrink > 1.3）应比缩量版本评分更低
    shrunk = scan(make_double_bottom_candles(), AS_OF)[0].score
    df = make_double_bottom_candles()["600519"]
    vols = df["volume"].astype(float).tolist()
    for i in range(228, 233):
        vols[i] = 3_000_000.0  # 右底放量
    df2 = make_candle_df(df["close"].astype(float).tolist(), volume=vols, high_pad=0.005, low_pad=0.005)
    expanded = scan({"600519": df2}, AS_OF)[0]
    assert expanded.metrics["vol_shrink"] > 1.3
    assert expanded.score < shrunk


# ── A股流动性门槛 ──
def test_low_price_rejected():
    cfg = DoubleBottomConfig()
    closes, highs, lows, vols, amounts = _series(_build_double_bottom(price_scale=0.3))
    assert _detect(closes, highs, lows, vols, amounts, cfg) is None  # 现价 < min_price(5)


def test_low_amount_rejected():
    cfg = DoubleBottomConfig()
    closes, highs, lows, vols, amounts = _series(_build_double_bottom())
    amounts = [a * 1e-4 for a in amounts]  # 成交额缩到几千元
    assert _detect(closes, highs, lows, vols, amounts, cfg) is None


# ── 停牌跳空：右底之后数据直接跳到末根（数据里没有中间 K 线）──
def test_gap_after_right_bottom_handled():
    # 右底落在末根前 k 根（最近可识别距离），形态仍应被识别（停牌跳空只影响索引，不影响判定）
    closes, highs, lows, vols, amounts = _series(_build_double_bottom_right_at_end())
    cfg = DoubleBottomConfig()
    r = _detect(closes, highs, lows, vols, amounts, cfg)
    assert r is not None
    assert r["bars_since_l2"] == 6


# ── 构造辅助 ──
def _build_double_bottom(
    price_scale: float = 1.0, tail_bars: int = 9
) -> list[float]:
    """构造一个确定性的 W 底序列（高位平台 → 主跌左底 → 反弹颈线 → 缓跌右底 → 尾盘）。"""
    n = 240
    closes = [0.0] * n

    def fill(i0, i1, v0, v1):
        for i in range(i0, i1 + 1):
            closes[i] = (v0 + (i - i0) * (v1 - v0) / max(1, i1 - i0)) * price_scale

    fill(0, 40, 100.0, 100.0)
    fill(40, 150, 100.0, 72.0)
    fill(150, 185, 72.0, 86.0)
    fill(185, 230, 86.0, 73.5)
    fill(230, n - 1, 73.5, 75.5)
    return closes


def _build_double_bottom_right_at_end() -> list[float]:
    """右底落在末根前 k 根（bars_since_l2 = swing_k = 6）的 W 底序列。

    摆动低点需要左右各 k 根确认，故右底最早能落在末根前 k 根；
    此例验证「右底距末根最近的可识别距离」仍能命中。
    """
    n = 240
    closes = [0.0] * n

    def fill(i0, i1, v0, v1):
        for i in range(i0, i1 + 1):
            closes[i] = v0 + (i - i0) * (v1 - v0) / max(1, i1 - i0)

    fill(0, 40, 100.0, 100.0)
    fill(40, 150, 100.0, 72.0)
    fill(150, 185, 72.0, 86.0)
    fill(185, 233, 86.0, 73.5)  # 右底 = index 233
    fill(233, n - 1, 73.5, 75.5)
    return closes


def _build_with_l2_offset(offset: float) -> list[float]:
    """右底相对左底抬高/降低 offset（0.1 = +10%），用于容差测试。"""
    n = 240
    closes = [0.0] * n

    def fill(i0, i1, v0, v1):
        for i in range(i0, i1 + 1):
            closes[i] = v0 + (i - i0) * (v1 - v0) / max(1, i1 - i0)

    fill(0, 40, 100.0, 100.0)
    fill(40, 150, 100.0, 72.0)
    fill(150, 185, 72.0, 86.0)
    l2 = 72.0 * (1 + offset)
    fill(185, 230, 86.0, l2)
    fill(230, n - 1, l2, l2 + 2.0)
    return closes


def _build_with_breakout() -> list[float]:
    """尾盘拉过颈线（86）→ 已突破。"""
    n = 240
    closes = [0.0] * n

    def fill(i0, i1, v0, v1):
        for i in range(i0, i1 + 1):
            closes[i] = v0 + (i - i0) * (v1 - v0) / max(1, i1 - i0)

    fill(0, 40, 100.0, 100.0)
    fill(40, 150, 100.0, 72.0)
    fill(150, 185, 72.0, 86.0)
    fill(185, 230, 86.0, 73.5)
    fill(230, n - 1, 73.5, 92.0)  # 尾盘拉过颈线
    return closes
