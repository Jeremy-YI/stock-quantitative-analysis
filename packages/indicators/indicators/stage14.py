"""阶段 14：MACD 柱状阶段顶底进出场 + 三条线降级为洗盘判别器（Jeremy 2026-08-29 定版）。

背景：阶段 13 把三条线当「入场过滤器」（站上生命线才能买），结果「修好机制不赚钱」——
等站上生命线 = 买在反弹之后，把深水抄底的 alpha 买丢了。

Jeremy 澄清的正确架构：
> 「大跌买 是 macd 阶段性底部，高点卖 是 macd 阶段性顶部。阴量定价线和生命线和进攻K
>   是用来辅助单针下30/20 是否是主力洗盘的。」

所以三条线**不参与入场判定**，它们是「洗盘 vs 破位」的判别器。

本模块提供以下纯函数原语（无 I/O、无前视）：

1. **柱状阶段性顶/底**（``detect_hist_stage_bottoms`` / ``detect_hist_stage_tops``）
   - 阶段性底部 = 绿柱（柱<0）最深值出现后开始收缩：
     ``柱[i] < 0 且 柱[i] > 柱[i-1] 且 柱[i-1] == 近 n 日最小``
   - 阶段性顶部 = 红柱（柱>0）最高值出现后开始收缩：
     ``柱[i] > 0 且 柱[i] < 柱[i-1] 且 柱[i-1] == 近 n 日最大``
   - n 测 5/10/20 三档。这是柱状体极值转折，不是金叉死叉，比金叉快。
   - 无前视：确认日 = 收缩的第一天（i），极值只用已收盘 bar（i-1）判定。
2. **破位容错**（``line_broken_2day``）：连续 2 个交易日收盘跌破才算破，单日破不算。
3. **三条线序列**（洗盘判别器的防线）：
   - 生命线 ``lifeline_series`` = (最近已确认顶背离区间最高 + 最近已确认底背离区间最低)/2。
   - 阴量定价线 ``yin_volume_line_series`` = 顶背离（摆动高点）附近区间内量最大阴线的最高价。
   - 进攻 K 防线 ``attack_defense_series`` = 进攻 K 中点，跳空开盘改用该 K 线最低价（栈逻辑）。

命名区分（与砖型图「黄线生命线」无关）：这里全部是 divergence 定价线，复用 stage13 的
k=3 区间化摆动点口径。
"""

from __future__ import annotations

from math import isnan, nan
from typing import Sequence

from indicators.divergence import swing_highs, swing_lows
from indicators.stage13 import attack_midpoint, detect_attack_candles

__all__ = [
    "DEFAULT_STAGE_N",
    "STAGE_NS",
    "detect_hist_stage_bottoms",
    "detect_hist_stage_tops",
    "line_broken_2day",
    "line_broken_1day",
    "lifeline_series",
    "yin_volume_line_series",
    "attack_defense_level",
    "attack_defense_series",
]


DEFAULT_STAGE_N = 5  # 柱状极值回看窗口（测 5/10/20 三档）
STAGE_NS = (5, 10, 20)
_DIV_K = 3  # 与 stage13 一致的区间化摆动点 k


# ----------------------------------------------------------------------------
# 1. 柱状阶段性顶/底
# ----------------------------------------------------------------------------


def detect_hist_stage_bottoms(
    hist: Sequence[float], n: int = DEFAULT_STAGE_N
) -> list[int]:
    """柱状阶段性底部确认日（绿柱最深值出现后开始收缩）。

    条件（i 为确认日 = 收缩第一天）：
        hist[i] < 0              绿柱
        hist[i] > hist[i-1]      收缩（比昨天浅）
        hist[i-1] == min(hist[i-n:i])  昨天是近 n 日最深绿柱

    无前视：极值只用已收盘 bar（i-1）判定，确认日就是 i，尾盘买用 i 收盘价。
    """
    h = list(hist)
    out: list[int] = []
    for i in range(n, len(h)):
        if h[i] < 0.0 and h[i] > h[i - 1]:
            win = h[i - n : i]
            if h[i - 1] <= min(win) + 1e-12:
                out.append(i)
    return out


def detect_hist_stage_tops(
    hist: Sequence[float], n: int = DEFAULT_STAGE_N
) -> list[int]:
    """柱状阶段性顶部确认日（红柱最高值出现后开始收缩）。与底部对称。"""
    h = list(hist)
    out: list[int] = []
    for i in range(n, len(h)):
        if h[i] > 0.0 and h[i] < h[i - 1]:
            win = h[i - n : i]
            if h[i - 1] >= max(win) - 1e-12:
                out.append(i)
    return out


# ----------------------------------------------------------------------------
# 2. 破位容错
# ----------------------------------------------------------------------------


def line_broken_2day(close: Sequence[float], line: float, t: int) -> bool:
    """破位容错：连续 2 个交易日收盘跌破才算破，单日破不算。

    即 close[t] < line 且 close[t-1] < line 才判「已破」。单日破（close[t] < line
    但 close[t-1] >= line）= 洗盘容错，不算破。t < 1 时视为不破（数据不足）。
    """
    if t < 1:
        return False
    return close[t] < line and close[t - 1] < line


def line_broken_1day(close: Sequence[float], line: float, t: int) -> bool:
    """单日破即算破（对照口径）。"""
    return t >= 0 and close[t] < line


# ----------------------------------------------------------------------------
# 3. 三条线序列
# ----------------------------------------------------------------------------


def lifeline_series(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    k: int = _DIV_K,
) -> list[float]:
    """生命线 = (最近已确认顶背离区间最高 + 最近已确认底背离区间最低)/2，前向填充。

    口径与 run_stage13.py 的 build_flags 逐行一致：
    - 顶背离区间最高 = 最近一个已确认摆动高点（k 根分形，确认日 = pivot + k）。
    - 底背离区间最低 = 最近一个「收盘创新低」的已确认摆动低点（不破底用收盘价）。
    - 两者都确认才定义，否则 NaN。
    """
    n = len(closes)
    sh = swing_highs(list(highs), k)
    sl = swing_lows(list(lows), k)

    top_high = [nan] * n
    for i in sorted(sh):
        cb = i + k
        if cb < n:
            for t in range(cb, n):
                top_high[t] = highs[i]

    bottom_low = [nan] * n
    prev_close: float | None = None
    ti = 0
    for i in sl:
        while ti < len(sh) and sh[ti] < i:
            ti += 1
        c = closes[i]
        is_new_low = prev_close is None or c < prev_close
        if is_new_low:
            cb = i + k
            if cb < n:
                for t in range(cb, n):
                    bottom_low[t] = lows[i]
        prev_close = c

    out: list[float] = []
    for t in range(n):
        th = top_high[t]
        bl = bottom_low[t]
        if (not isnan(th)) and (not isnan(bl)):
            out.append((th + bl) / 2.0)
        else:
            out.append(nan)
    return out


def yin_volume_line_series(
    highs: Sequence[float],
    lows: Sequence[float],
    opens: Sequence[float],
    closes: Sequence[float],
    vols: Sequence[float],
    k: int = _DIV_K,
) -> list[float]:
    """阴量定价线：最近已确认顶背离（摆动高点）附近区间内量最大阴线的最高价。

    口径（规格「指标1」+ 阶段12 V2P1 代表口径）：
    - 锚点 = 摆动高点（k 根分形），确认日 = pivot + k。
    - 区间 = [上一个摆动低点, 该摆动高点]（上涨腿）。
    - 阴线 = close < open；定价线 = 该阴线**最高价**（V2P1）。
    - 前向填充（确认日之后才可用，无前视）。
    """
    n = len(closes)
    sh = swing_highs(list(highs), k)
    sl = swing_lows(list(lows), k)
    out = [nan] * n

    for hi in sh:
        # 上一个摆动低点（区间下界）
        prev_low = -1
        for s in sl:
            if s < hi:
                prev_low = s
            else:
                break
        lo = prev_low if prev_low >= 0 else max(0, hi - 2 * k)
        best = -1
        best_vol = -1.0
        for j in range(lo, hi + 1):
            if closes[j] < opens[j]:  # 阴线
                if vols[j] > best_vol:
                    best_vol = vols[j]
                    best = j
        if best < 0:
            continue
        cb = hi + k
        if cb < n:
            for t in range(cb, n):
                out[t] = highs[best]
    return out


def attack_defense_level(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    atk_idx: int,
) -> float:
    """进攻 K 防线：跳空开盘（开盘 > 前日最高）→ 用该跳空 K 线最低价，否则用中点。

    Jeremy 澄清：个股进攻 K = 涨停板（收盘=涨停价），所以 (开+收)/2 与 (开+涨停)/2 等价，
    现有中点公式正确不用改；但跳空开盘时主力防线改用跳空 K 线最低价（不是中点）。
    """
    if atk_idx > 0 and opens[atk_idx] > highs[atk_idx - 1]:
        return lows[atk_idx]
    return attack_midpoint(opens[atk_idx], closes[atk_idx])


def attack_defense_series(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    symbol: str = "main",
) -> list[float]:
    """逐日「当前有效进攻 K 防线」序列（栈逻辑 + 跳空处理），无进攻 K 处为 NaN。

    - 进攻 K 用 stage13.detect_attack_candles（品种阈值）。
    - 防线 = attack_defense_level（跳空开→最低价，否则中点）。
    - 栈逻辑：当前有效 = 最近一个尚未被收盘跌破防线的进攻 K；破了出栈回退。
    """
    n = len(closes)
    atk = detect_attack_candles(list(opens), list(closes), symbol)
    atk_set = set(atk)
    def_of = {i: attack_defense_level(opens, highs, lows, closes, i) for i in atk}
    series = [nan] * n
    stack: list[int] = []
    for i in range(n):
        if i in atk_set:
            stack.append(i)
        while stack and closes[i] < def_of[stack[-1]]:
            stack.pop()
        if stack:
            series[i] = def_of[stack[-1]]
    return series
