"""背离检测模块（indicators.divergence）单测。

覆盖点（阶段 12）：
1. ``swing_lows`` 与 ``strategies.double_bottom.swing_lows`` 逐行一致。
2. ``swing_highs`` 是 ``swing_lows`` 的对称（把低点翻成负号即高点）。
3. 底背离：右底齐平/略高但 DIF 抬升（DIF 硬条件 + 三取二）。
4. 顶背离：右高创新高/齐平但 DIF 走低。
5. 已确认时点 = 右 pivot + k（无前视：confirmed_bar > i2）。
"""

from __future__ import annotations

import numpy as np

from indicators.divergence import (
    detect_bearish_divergences,
    detect_bullish_divergences,
    swing_highs,
    swing_lows,
)
from strategies.double_bottom.strategy import swing_lows as db_swing_lows


def test_swing_lows_matches_double_bottom() -> None:
    rng = np.random.default_rng(0)
    lows = (rng.random(300) * 100).tolist()
    assert swing_lows(lows, 6) == db_swing_lows(lows, 6)


def test_swing_highs_symmetric() -> None:
    rng = np.random.default_rng(1)
    highs = (rng.random(300) * 100).tolist()
    neg = [-h for h in highs]
    # 高点 = 负低点的负值：swing_highs(highs) == swing_lows(-highs)
    assert swing_highs(highs, 6) == swing_lows(neg, 6)


def _macd_like_rising() -> list[float]:
    """一条单调抬升的 DIF（用于构造底背离）。"""
    return [float(i) * 0.01 for i in range(200)]


def _zigzag(points: list[tuple[int, float]], n: int) -> list[float]:
    """按关键点线性插值出长度为 n 的序列（严格单调段，无平台）。"""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    out = []
    for i in range(n):
        if i <= xs[0]:
            out.append(ys[0])
        elif i >= xs[-1]:
            out.append(ys[-1])
        else:
            for a in range(len(xs) - 1):
                if xs[a] <= i <= xs[a + 1]:
                    t = (i - xs[a]) / (xs[a + 1] - xs[a])
                    out.append(ys[a] + (ys[a + 1] - ys[a]) * t)
                    break
    return out


def test_bullish_divergence_confirmed_bar() -> None:
    n = 200
    k = 6
    # 两个摆动低点：i1=40（10.0）、i2=120（10.1 略高=不破底，+1% < tol 3%），中间一个高点 i=80
    lows = _zigzag([(0, 40), (40, 10), (80, 30), (120, 10.1), (199, 40)], n)
    dif = _macd_like_rising()  # dif 单调抬升 → dif[i2] > dif[i1]
    hist = [0.1 + i * 0.001 for i in range(n)]  # 柱也抬升 → div_count=2
    rsi = [50.0] * n
    divs = detect_bullish_divergences(lows, dif, hist, rsi, k=k)
    assert divs, "应识别到底背离"
    d = divs[0]
    assert d.kind == "bullish"
    assert d.i1 == 40 and d.i2 == 120
    assert d.confirmed_bar == d.i2 + k  # 无前视
    assert d.osc_rising is True


def test_bearish_divergence_confirmed_bar() -> None:
    n = 200
    k = 6
    # 两个摆动高点：i1=40（40.0）、i2=120（41.0 创新高），中间一个低点 i=80
    highs = _zigzag([(0, 10), (40, 40), (80, 20), (120, 41), (199, 15)], n)
    dif = [-float(i) * 0.01 for i in range(n)]  # dif 单调走低 → dif[i2] < dif[i1]
    hist = [0.0] * n
    divs = detect_bearish_divergences(highs, dif, hist, k=k)
    assert divs, "应识别到顶背离"
    d = divs[0]
    assert d.kind == "bearish"
    assert d.i1 == 40 and d.i2 == 120
    assert d.confirmed_bar == d.i2 + k
    assert d.osc_rising is False


def test_no_divergence_when_dif_flat() -> None:
    n = 200
    k = 6
    lows = _zigzag([(0, 40), (40, 10), (80, 30), (120, 10.1), (199, 40)], n)
    dif = [0.5] * n  # DIF 不抬升 → 底背离 DIF 硬条件不成立
    hist = [0.1] * n
    rsi = [50.0] * n
    assert detect_bullish_divergences(lows, dif, hist, rsi, k=k) == []
