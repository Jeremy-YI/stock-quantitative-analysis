"""3-2-2-2 分步建仓单元测试：分步 vs 一次性建仓的建仓笔数 / 首档比例。"""

from __future__ import annotations

from datetime import date

import pytest

from backtest.config import BacktestConfig
from backtest.portfolio import simulate_portfolio
from strategies.signal import Signal
from tests.helpers import make_candle_df

D0 = date(2026, 8, 24)  # 周一（信号触发日）


def _flat_candles(n: int = 12, price: float = 10.0) -> dict:
    """构造 n 根平盘日线（避免涨跌停 / 止盈止损干扰）。"""
    return {"600000": make_candle_df([price] * n, start=D0, volume=1000.0)}


def _signal() -> Signal:
    return Signal(symbol="600000", strategy="b1b2b3", signal_type="b1", score=1.0, triggered_at=D0)


def _config(stepwise=None, hold: int = 8) -> BacktestConfig:
    cfg = BacktestConfig()
    cfg.portfolio.max_holding_days = hold
    cfg.portfolio.stop_loss_pct = -0.5
    cfg.portfolio.take_profit_pct = 0.5
    cfg.portfolio.position_weight = 0.20
    cfg.portfolio.reserve_ratio = 0.20
    if stepwise is not None:
        cfg.portfolio.stepwise_tranches = stepwise
    return cfg


def test_one_shot_buys_once():
    report = simulate_portfolio([_signal()], _flat_candles(), _config(stepwise=None))
    assert report["filled_buys"] == 1


def test_stepwise_fills_four_tranches():
    # 3-2-2-2：首档 + 三次加仓 = 4 笔
    report = simulate_portfolio(
        [_signal()], _flat_candles(), _config(stepwise=(0.3, 0.2, 0.2, 0.2), hold=8)
    )
    assert report["filled_buys"] == 4


def test_stepwise_deploys_less_than_full_budget():
    """分步建仓合计只下 90%（30+20+20+20），比一次性少下 10%。"""
    candles = _flat_candles()
    one = simulate_portfolio([_signal()], candles, _config(stepwise=None))
    step = simulate_portfolio(
        [_signal()], candles, _config(stepwise=(0.3, 0.2, 0.2, 0.2), hold=8)
    )
    # 平盘下：分步建仓的最终权益高于一次性（少部署的现金留在账上）
    assert step["equity_curve"][-1]["equity"] > one["equity_curve"][-1]["equity"]


def test_stepwise_tranche_gap_respects_interval():
    """间隔 2 日：4 档需要更长时间，8 个交易日内不足以全部建满。"""
    report = simulate_portfolio(
        [_signal()], _flat_candles(), _config(stepwise=(0.3, 0.2, 0.2, 0.2), hold=8)
    )
    cfg2 = _config(stepwise=(0.3, 0.2, 0.2, 0.2), hold=8)
    cfg2.portfolio.stepwise_interval_days = 3
    report2 = simulate_portfolio([_signal()], _flat_candles(), cfg2)
    # 间隔 3 日时，第 2/3/4 档分别在 +3/+6/+9 日，9 日 > 8 日持有期，建不满 4 档
    assert report2["filled_buys"] < report["filled_buys"]
