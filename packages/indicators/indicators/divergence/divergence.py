"""背离检测模块（阶段 12 新增）。

规格：``~/.openclaw/workspace/specs/背离定价线指标规格.md``。

提供两类纯函数：

1. **摆动点**：``swing_lows`` / ``swing_highs`` —— 左右各 k 根的分形低点/高点，
   相邻的合并取更极端者。``swing_lows`` 与 ``strategies.double_bottom.swing_lows``
   逐行一致，``swing_highs`` 是其对称版本。

2. **背离确认**：
   - 底背离 ``detect_bullish_divergences``：沿用 double_bottom 现有口径 ——
     DIF/柱/RSI 三项里至少 2 项抬升，DIF 抬升为硬条件（全项目一致）。
   - 顶背离 ``detect_bearish_divergences``：与底背离对称 —— 相邻两 pivot high，
     价格创新高（或齐平）但 DIF 明显走低（红柱面积 A2<A1 为可选加分，不作为硬条件）。

关键约束（前视偏差）：背离的「已确认」时点 = 右侧 pivot 成形（pivot 索引 + k 根）之后。
回测只能在这个时点之后才可用该背离，否则是前视。因此每个检测结果都带
``confirmed_bar``（右侧 pivot 之后第 k 根），调用方只能在此之后触发动作。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Divergence:
    """一笔已识别的背离（已确认时点 = confirmed_bar）。"""

    kind: str  # "bullish" / "bearish"
    i1: int  # 左侧 pivot 索引
    i2: int  # 右侧 pivot 索引
    confirmed_bar: int  # 右侧 pivot 成形（i2+k）之后的索引，回测只能用此后的数据
    p1: float
    p2: float
    osc1: float
    osc2: float
    osc_rising: bool  # 振荡指标是否抬升（bullish=True / bearish=False）
    div_count: int  # 参与判定的指标里「抬升/走低」的个数（底背离 2~3，顶背离 1~2）


def swing_lows(lows: list[float], k: int) -> list[int]:
    """找摆动低点（局部极小值）：左右各 k 根都不低于它，相邻合并取更低。

    与 ``strategies.double_bottom.swing_lows`` 逐行一致。
    """
    n = len(lows)
    if n < 2 * k + 1:
        return []
    raw: list[int] = []
    for i in range(k, n - k):
        if lows[i] == min(lows[i - k : i + k + 1]):
            raw.append(i)
    merged: list[int] = []
    for i in raw:
        if merged and i - merged[-1] < k:
            if lows[i] < lows[merged[-1]]:
                merged[-1] = i
        else:
            merged.append(i)
    return merged


def swing_highs(highs: list[float], k: int) -> list[int]:
    """找摆动高点（局部极大值）：左右各 k 根都不高于它，相邻合并取更高。

    ``swing_lows`` 的对称版本。
    """
    n = len(highs)
    if n < 2 * k + 1:
        return []
    raw: list[int] = []
    for i in range(k, n - k):
        if highs[i] == max(highs[i - k : i + k + 1]):
            raw.append(i)
    merged: list[int] = []
    for i in raw:
        if merged and i - merged[-1] < k:
            if highs[i] > highs[merged[-1]]:
                merged[-1] = i
        else:
            merged.append(i)
    return merged


def detect_bullish_divergences(
    lows: list[float],
    dif: list[float],
    hist: list[float],
    rsi: list[float],
    k: int = 6,
    tol_higher: float = 0.03,
    tol_lower: float = 0.03,
    min_div_count: int = 2,
) -> list[Divergence]:
    """底背离：相邻两摆动低点，右底齐平或略高（不破底）但 DIF/柱/RSI 抬升。

    口径与 double_bottom 一致：DIF 抬升为硬条件，且 DIF/柱/RSI 三项至少
    ``min_div_count`` 项抬升（默认 2）。
    """
    sl = swing_lows(lows, k)
    out: list[Divergence] = []
    for a in range(len(sl) - 1):
        i1, i2 = sl[a], sl[a + 1]
        l1, l2 = lows[i1], lows[i2]
        if l1 <= 0:
            continue
        diff = (l2 - l1) / l1
        if diff > tol_higher or diff < -tol_lower:
            continue
        dif_up = dif[i2] > dif[i1]
        hist_up = hist[i2] > hist[i1]
        rsi_up = rsi[i2] > rsi[i1]
        if not dif_up:
            continue
        div_count = sum((dif_up, hist_up, rsi_up))
        if div_count < min_div_count:
            continue
        out.append(
            Divergence(
                kind="bullish",
                i1=i1,
                i2=i2,
                confirmed_bar=i2 + k,
                p1=l1,
                p2=l2,
                osc1=dif[i1],
                osc2=dif[i2],
                osc_rising=True,
                div_count=div_count,
            )
        )
    return out


def detect_bearish_divergences(
    highs: list[float],
    dif: list[float],
    hist: list[float],
    k: int = 6,
    tol_lower: float = 0.0,
    min_dif_drop_ratio: float = 0.0,
) -> list[Divergence]:
    """顶背离：相邻两摆动高点，价格创新高（或齐平）但 DIF 明显走低。

    - 价格：P2 >= P1 * (1 - tol_lower)，默认 tol_lower=0（严格不破前高，即创新高或齐平）。
    - 振荡：DIF2 < DIF1 * (1 - min_dif_drop_ratio)，默认 0（严格走低）。
    - 红柱面积 A2 < A1（hist 走低）作为额外计数，不作为硬条件（与底背离对称）。
    """
    sh = swing_highs(highs, k)
    out: list[Divergence] = []
    for a in range(len(sh) - 1):
        i1, i2 = sh[a], sh[a + 1]
        p1, p2 = highs[i1], highs[i2]
        if p1 <= 0:
            continue
        if p2 < p1 * (1.0 - tol_lower):
            continue
        if dif[i2] >= dif[i1] * (1.0 - min_dif_drop_ratio):
            continue
        hist_down = hist[i2] < hist[i1]
        out.append(
            Divergence(
                kind="bearish",
                i1=i1,
                i2=i2,
                confirmed_bar=i2 + k,
                p1=p1,
                p2=p2,
                osc1=dif[i1],
                osc2=dif[i2],
                osc_rising=False,
                div_count=2 if hist_down else 1,
            )
        )
    return out
