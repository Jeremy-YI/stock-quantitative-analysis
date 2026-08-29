"""阶段 13：区间化背离 + 双防线入场/止损体系（Jeremy 2026-08-29 定版）。

核心口径（Jeremy 澄清五条，逐条用本地数据验证通过）：

1. **背离是 2-3 天的区间，不是单根 K 线**。锚点 = 区间内极值，确认日可以更晚。
   - pivot 用左右各 k 根确认（k=1/2/3 可测），锚点取窗口极值，确认日 = pivot + k。
   - 159828 案例用 k=3 复现全部点位（顶背离 3/17 高 4.27 / 5/21 高 4.17；
     底背离 3/23 低 3.84 / 6/09 低 3.59）。
2. **MACD 用收盘价算，盘中无法确认背离 → 只能尾盘买**。回测买入价必须用确认日收盘价。
3. **进攻 K 中点公式 = (开盘+收盘)/2**（不是 (高+低)/2）。6/29 开3.68 收3.87 → 3.775。
4. **「增量资金」**：价格继续新低，但 MACD 绿柱最深值变浅 + 连续收缩。
5. **不破底用收盘价**：盘中破、收盘不破 = 不算破，反而算承接。

修正后的入场序列（四步）：
    ① 底背离确认（区间二次探底不破 + 绿柱最深值变浅）
    ② 价格收盘站上生命线（生命线 = (最近已确认顶背离区间最高 + 最近已确认底背离区间最低)/2）
    ③ 单针下 30/20 触发（短期随机 ≤30 或 ≤20）
    ④ 买入（用当日收盘价）

双防线止损体系：
    - 第一道 生命线：收盘跌破 → 减仓；2-3 日内收盘重新站回 → 洗盘，买回。
    - 第二道 进攻 K 中点（栈逻辑：当前有效 = 最近一个未收盘跌破中点的进攻 K）：收盘跌破 → 离场。

长上影线卖出：上影线长度 ÷ (高-低) ≥ 阈值（测 50/60/70%）→ 卖出 ≥50% 仓位。

命名区分（与砖型图「黄线生命线」无关）：这里全部是 divergence 定价线。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from indicators.divergence import swing_highs, swing_lows

__all__ = [
    "BottomDivergence",
    "TopDivergence",
    "detect_bottom_divergences",
    "detect_top_divergences",
    "lifeline_value",
    "detect_attack_candles",
    "attack_midpoint",
    "attack_stack",
    "current_attack_midpoint",
    "upper_shadow_ratio",
    "is_long_upper_shadow",
    "DEFAULT_K",
]


DEFAULT_K = 3  # 区间化背离的左右各 k 根确认（159828 用 k=3 复现全部点位）

# 进攻 K 涨幅阈值（按品种，Jeremy 2026-08-29 定版）
ATTACK_THRESHOLD = {
    "main": 0.10,      # 主板 600/601/603/605/000/001/002
    "star": 0.20,      # 科创板 688 / 创业板 300/301
    "etf": 0.04,       # ETF
    "bse": None,       # 北交所：不看，直接排除
}


@dataclass
class BottomDivergence:
    """一笔已确认的底背离（区间二次探底）。

    - ``idx``：摆动低点索引（锚点 = 区间最低价 ``low``）。
    - ``confirm_bar``：确认日 = idx + k（回测只能在此之后用，无前视）。
    - ``top_idx``：紧邻其前的摆动高点索引（顶背离），用于生命线。
    - ``is_new_low``：是否相对前一个摆动低点收盘创新低（不破底 = 收盘价口径）。
    """

    idx: int
    low: float
    close: float
    confirm_bar: int
    top_idx: int
    top_high: float
    is_new_low: bool


@dataclass
class TopDivergence:
    """一笔顶背离（区间顶），锚点 = 区间最高价 ``high``。"""

    idx: int
    high: float
    confirm_bar: int


def detect_bottom_divergences(
    lows: list[float],
    closes: list[float],
    highs: list[float] | None = None,
    k: int = DEFAULT_K,
) -> list[BottomDivergence]:
    """底背离：摆动低点（区间二次探底）。

    口径：
    - 摆动低点用左右各 ``k`` 根分形（``swing_lows``），锚点 = 区间最低价。
    - 「不破底用收盘价」：相对前一个摆动低点的**收盘价**创新低才算新的底
      （盘中破、收盘不破 → 不算破，反而算承接）。
    - 确认日 = idx + k（无前视）。
    - 顶背离 = 紧邻该低点之前的摆动高点（用于生命线），需 ``highs`` 传入。
    """
    sl = swing_lows(lows, k)
    sh = swing_highs(highs, k) if highs is not None else []
    n = len(lows)

    out: list[BottomDivergence] = []
    prev_close: float | None = None
    # 顶背离指针：随低点推进，取最后一个 < idx 的摆动高点
    ti = 0
    for idx in sl:
        while ti < len(sh) and sh[ti] < idx:
            ti += 1
        top_idx = sh[ti - 1] if ti > 0 else -1
        top_high = highs[top_idx] if top_idx >= 0 else 0.0

        c = closes[idx]
        is_new_low = prev_close is None or c < prev_close
        out.append(
            BottomDivergence(
                idx=idx,
                low=lows[idx],
                close=c,
                confirm_bar=idx + k if idx + k < n else n - 1,
                top_idx=top_idx,
                top_high=top_high,
                is_new_low=is_new_low,
            )
        )
        prev_close = c
    return out


def detect_top_divergences(
    highs: list[float],
    k: int = DEFAULT_K,
) -> list[TopDivergence]:
    """顶背离：摆动高点（区间顶），锚点 = 区间最高价，确认日 = idx + k。"""
    sh = swing_highs(highs, k)
    n = len(highs)
    return [
        TopDivergence(idx=i, high=highs[i], confirm_bar=i + k if i + k < n else n - 1)
        for i in sh
    ]


def lifeline_value(top_high: float, bottom_low: float) -> float:
    """生命线 = (最近已确认顶背离区间最高 + 最近已确认底背离区间最低) / 2。"""
    return (top_high + bottom_low) / 2.0


# ----------------------------------------------------------------------------
# 进攻 K（attack candle）
# ----------------------------------------------------------------------------


def attack_midpoint(open_: float, close: float) -> float:
    """进攻 K 中点 = (开盘 + 收盘) / 2。"""
    return (open_ + close) / 2.0


def attack_kind(symbol: str) -> str | None:
    """按代码前缀返回品种档位（main / star / etf / bse），北交所返回 None（排除）。"""
    s = symbol.upper()
    if s.startswith("SH") or s.startswith("SZ"):
        s = s[2:]
    if s.startswith(("688", "300", "301")):
        return "star"
    if s.startswith(("600", "601", "603", "605", "000", "001", "002")):
        return "main"
    # ETF / 指数 / 其他
    if s.startswith(("15", "16", "51", "56", "58")) or len(s) == 6 and s[0] in "159":
        return "etf"
    if s.startswith(("43", "83", "87", "88", "92")):
        return "bse"
    return "etf" if len(s) < 6 else "main"


def detect_attack_candles(
    opens: list[float],
    closes: list[float],
    symbol: str = "main",
) -> list[int]:
    """找出所有进攻 K（单日涨幅 ≥ 品种阈值的 K 线），返回索引列表（升序）。

    阈值：main ≥10%、star ≥20%、etf ≥4%、bse 排除。
    """
    kind = attack_kind(symbol) if symbol not in ("main", "star", "etf", "bse") else symbol
    thr = ATTACK_THRESHOLD.get(kind)
    if thr is None:
        return []
    idx: list[int] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev <= 0:
            continue
        if (closes[i] / prev - 1.0) >= thr:
            idx.append(i)
    return idx


def attack_stack(
    attack_indices: list[int],
    closes: list[float],
    midpoints: list[float],
) -> list[int]:
    """进攻 K 栈逻辑（逐日模拟）：当前有效 = 最近一个尚未被收盘跌破中点的进攻 K。

    返回与 ``attack_indices`` 等长的「有效性」列表（1=序列末仍在栈内，0=已出栈）。
    「未破」用收盘价：任一日的收盘 < 栈顶中点 → 出栈（回退到上一个）。
    失败的进攻 K 不覆盖前一个有效的（破了就出栈，回退）。
    """
    atk_pos = {ai: p for p, ai in enumerate(attack_indices)}
    stack: list[int] = []  # 存 attack_indices 里的位置
    for i, c in enumerate(closes):
        if i in atk_pos:
            stack.append(atk_pos[i])
        while stack and c < midpoints[attack_indices[stack[-1]]]:
            stack.pop()
    valid = [0] * len(attack_indices)
    for p in stack:
        valid[p] = 1
    return valid


def current_attack_midpoint(
    attack_indices: list[int],
    closes: list[float],
    midpoints: list[float],
    bar: int,
) -> float | None:
    """截至 ``bar``（含）当前有效的进攻 K 中点（栈逻辑，逐日）；无则 None。"""
    atk_set = set(attack_indices)
    stack: list[float] = []
    for i in range(bar + 1):
        if i in atk_set:
            stack.append(midpoints[i])
        while stack and closes[i] < stack[-1]:
            stack.pop()
    return stack[-1] if stack else None


# ----------------------------------------------------------------------------
# 长上影线
# ----------------------------------------------------------------------------


def upper_shadow_ratio(open_: float, high: float, low: float, close: float) -> float:
    """上影线长度 ÷ (高 - 低)。上影 = 高 - max(开, 收)。"""
    rng = high - low
    if rng <= 0:
        return 0.0
    body_top = max(open_, close)
    return (high - body_top) / rng


def is_long_upper_shadow(
    open_: float,
    high: float,
    low: float,
    close: float,
    threshold: float = 0.6,
) -> bool:
    """是否长上影线（上影占比 ≥ 阈值）。"""
    return upper_shadow_ratio(open_, high, low, close) >= threshold
