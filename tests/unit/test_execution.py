"""成交与成本计算单元测试（手工算好期望值断言）。"""

from __future__ import annotations

import pytest

from backtest.config import CostConfig
from backtest.execution import (
    apply_slippage,
    buy_cost,
    can_buy_at_open,
    can_sell_at_close,
    commission,
    is_shanghai,
    limit_down_price,
    limit_up_price,
    round_trip_net_return,
    sell_cost,
    stamp_tax,
    transfer_fee,
)


def test_limit_up_price_mainboard():
    # 主板 ±10%，四舍五入到分
    assert limit_up_price(10.0, "600519") == 11.0
    assert limit_down_price(10.0, "600519") == 9.0


def test_limit_up_price_chinext():
    # 创业板 ±20%
    assert limit_up_price(10.0, "300750") == 12.0
    assert limit_down_price(10.0, "300750") == 8.0


def test_limit_up_price_st():
    assert limit_up_price(10.0, "600519", is_st=True) == 10.5
    assert limit_down_price(10.0, "600519", is_st=True) == 9.5


def test_limit_price_rounding():
    # 10.03 * 1.10 = 11.033 → 11.03
    assert limit_up_price(10.03, "600519") == 11.03


def test_can_buy_at_open_reject_limit_up():
    # 开盘一字涨停（open == 涨停价）买不进
    assert can_buy_at_open(11.0, 10.0, "600519") is False
    # 略低于涨停价可以买
    assert can_buy_at_open(10.99, 10.0, "600519") is True


def test_can_buy_at_open_invalid_prev_close():
    assert can_buy_at_open(11.0, 0.0, "600519") is False


def test_can_sell_at_close_reject_limit_down():
    # 收盘封死跌停卖不出
    assert can_sell_at_close(9.0, 10.0, "600519") is False
    assert can_sell_at_close(9.01, 10.0, "600519") is True


def test_is_shanghai():
    assert is_shanghai("600519") is True
    assert is_shanghai("688001") is True
    assert is_shanghai("000001") is False
    assert is_shanghai("300750") is False


def test_commission_min_5():
    cost = CostConfig()
    # 万 2.5：10000 元成交 → 2.5 元，低于最低 5 元 → 收 5 元
    assert commission(10000.0, cost) == 5.0
    # 30 万元成交 → 75 元，超过最低 → 收 75 元
    assert commission(300_000.0, cost) == 75.0


def test_stamp_tax_sell_only():
    cost = CostConfig()
    assert stamp_tax(10000.0, cost) == 10.0  # 千 1


def test_transfer_fee_shanghai_only():
    cost = CostConfig()
    assert transfer_fee(10000.0, "600519", cost) == 0.1  # 万 0.1
    assert transfer_fee(10000.0, "000001", cost) == 0.0


def test_buy_cost_hand_computed():
    cost = CostConfig()
    # 沪市买 1000 股 @10 元：佣金 max(2.5,5)=5 + 过户 10000*0.00001=0.1
    assert buy_cost(10000.0, "600519", cost) == 5.1
    # 深市无过户费
    assert buy_cost(10000.0, "000001", cost) == 5.0


def test_sell_cost_hand_computed():
    cost = CostConfig()
    # 沪市卖 1000 股 @12 元（12000）：佣金 max(3,5)=5 + 印花 12 + 过户 0.12
    assert sell_cost(12000.0, "600519", cost) == 17.12
    # 深市：5 + 12 = 17.0
    assert sell_cost(12000.0, "000001", cost) == 17.0


def test_apply_slippage():
    cost = CostConfig()
    assert apply_slippage(10.0, "buy", cost) == pytest.approx(10.01, abs=1e-9)
    assert apply_slippage(10.0, "sell", cost) == pytest.approx(9.99, abs=1e-9)


def test_round_trip_net_return_hand_computed():
    cost = CostConfig()
    # 沪市 1000 股：买 @10（滑点后 10.01），卖 @12（滑点后 11.988）
    # 买成交 10010，成本 5.1001（佣金 5 + 过户 0.1001）
    # 卖成交 11988，成本 17.10788（佣金 5 + 印花 11.988 + 过户 0.11988）
    # 净收益 = (11988 - 17.10788) / (10010 + 5.1001) - 1
    ret = round_trip_net_return("600519", 10.0, 12.0, 1000.0, cost)
    assert ret == pytest.approx(0.1952843, abs=1e-6)
