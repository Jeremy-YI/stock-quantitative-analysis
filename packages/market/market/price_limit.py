"""A股涨跌停幅度规则（百分比，写进代码而非散落的魔法数字）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PriceLimit:
    """涨跌停幅度（百分数）。up 为涨停幅度（正），down 为跌停幅度（负）。"""

    up: float
    down: float


def get_price_limit(symbol: str, is_st: bool = False) -> PriceLimit:
    """按板块返回涨跌停幅度。

    规则：
        ST/*ST           ±5%
        创业板(30) 科创板(68)  ±20%
        北交所(43/83/87/88/92) ±30%
        主板(60/00)      ±10%（默认）
    """
    if is_st:
        return PriceLimit(up=5.0, down=-5.0)
    if symbol.startswith(("30", "68")):
        return PriceLimit(up=20.0, down=-20.0)
    if symbol.startswith(("43", "83", "87", "88", "92")):
        return PriceLimit(up=30.0, down=-30.0)
    return PriceLimit(up=10.0, down=-10.0)
