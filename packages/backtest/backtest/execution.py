"""成交与成本计算（纯函数，A股真实约束）。

集中处理回测里「像不像国内做的」的关键约束：

    - 涨跌停价：按板块幅度四舍五入到分（0.01 元）。
    - 一字涨停买不进：开盘价触及涨停价即无法在开盘买入。
    - 跌停卖不出：收盘价触及跌停价即无法在收盘卖出。
    - 交易成本：佣金（最低 5 元）+ 印花税（卖出）+ 过户费（沪市）+ 滑点。

全部为无副作用的纯函数，便于单测手工算期望值断言。
"""

from __future__ import annotations

from market.price_limit import get_price_limit

from .config import CostConfig

# 沪市代码前缀（过户费仅沪市收取）
_SH_PREFIXES = ("60", "68")

# 涨跌停价判定用的小容差（浮点/舍入误差）
_PRICE_EPS = 0.001


def limit_price(prev_close: float, pct: float) -> float:
    """按涨跌停幅度计算限价，四舍五入到分（0.01 元）。

    A股价格最小变动 0.01 元，涨跌停价 = round(昨收 * (1 + 幅度%)，2)。
    """
    return round(prev_close * (1.0 + pct / 100.0), 2)


def limit_up_price(prev_close: float, symbol: str, is_st: bool = False) -> float:
    """涨停价。"""
    pl = get_price_limit(symbol, is_st)
    return limit_price(prev_close, pl.up)


def limit_down_price(prev_close: float, symbol: str, is_st: bool = False) -> float:
    """跌停价。"""
    pl = get_price_limit(symbol, is_st)
    return limit_price(prev_close, pl.down)


def can_buy_at_open(
    open_price: float, prev_close: float, symbol: str, is_st: bool = False
) -> bool:
    """判断开盘是否能买入。

    开盘价触及涨停价（一字涨停 / 开盘即涨停）时无法在开盘成交，返回 False。
    """
    if prev_close <= 0:
        return False
    return open_price < limit_up_price(prev_close, symbol, is_st) - _PRICE_EPS


def can_sell_at_close(
    close_price: float, prev_close: float, symbol: str, is_st: bool = False
) -> bool:
    """判断收盘是否能卖出。

    收盘价触及跌停价（封死跌停）时卖单无法成交，返回 False。
    """
    if prev_close <= 0:
        return False
    return close_price > limit_down_price(prev_close, symbol, is_st) + _PRICE_EPS


def is_shanghai(symbol: str) -> bool:
    """是否沪市标的（过户费仅沪市收取）。"""
    return symbol.startswith(_SH_PREFIXES)


def commission(turnover: float, cost: CostConfig) -> float:
    """佣金：费率 * 成交额，单笔最低 5 元。"""
    return max(turnover * cost.commission_rate, cost.min_commission)


def stamp_tax(turnover: float, cost: CostConfig) -> float:
    """印花税：卖出单边千 1（买入不收）。"""
    return turnover * cost.stamp_tax_rate


def transfer_fee(turnover: float, symbol: str, cost: CostConfig) -> float:
    """过户费：沪市万分之 0.1（双边）。"""
    if not is_shanghai(symbol):
        return 0.0
    return turnover * cost.transfer_fee_rate


def buy_cost(turnover: float, symbol: str, cost: CostConfig) -> float:
    """买入成本 = 佣金 + 过户费（无印花税）。"""
    return commission(turnover, cost) + transfer_fee(turnover, symbol, cost)


def sell_cost(turnover: float, symbol: str, cost: CostConfig) -> float:
    """卖出成本 = 佣金 + 印花税 + 过户费。"""
    return (
        commission(turnover, cost)
        + stamp_tax(turnover, cost)
        + transfer_fee(turnover, symbol, cost)
    )


def apply_slippage(price: float, side: str, cost: CostConfig) -> float:
    """叠加滑点：买入加价、卖出减价（都更不利）。"""
    if side == "buy":
        return price * (1.0 + cost.slippage)
    if side == "sell":
        return price * (1.0 - cost.slippage)
    raise ValueError(f"side 必须是 buy/sell，收到 {side!r}")


def round_trip_net_return(
    symbol: str,
    buy_price: float,
    sell_price: float,
    qty: float,
    cost: CostConfig,
) -> float:
    """一次完整买卖的净收益率（相对投入资金）。

    买入价叠加买入滑点，卖出价叠加卖出滑点，两边分别计成本。
    """
    buy_px = apply_slippage(buy_price, "buy", cost)
    sell_px = apply_slippage(sell_price, "sell", cost)
    buy_turnover = buy_px * qty
    sell_turnover = sell_px * qty
    buy_fee = buy_cost(buy_turnover, symbol, cost)
    sell_fee = sell_cost(sell_turnover, symbol, cost)

    invested = buy_turnover + buy_fee
    proceeds = sell_turnover - sell_fee
    if invested <= 0:
        return 0.0
    return proceeds / invested - 1.0
