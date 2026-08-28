"""组合回测单元测试：T+1 / 涨跌停 / 成本落地。"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from backtest.config import BacktestConfig
from backtest.portfolio import (
    _build_buy_groups,
    _eligible_strategies,
    _strategy_shares,
    simulate_portfolio,
)
from strategies.signal import Signal

D0 = date(2026, 8, 24)  # 周一
D1 = date(2026, 8, 25)
D2 = date(2026, 8, 26)
D3 = date(2026, 8, 27)


def _df(dates: list[date], opens: list[float], closes: list[float]) -> pd.DataFrame:
    """构造日线（high/low 取 open/close 的略高略低）。"""
    return pd.DataFrame(
        {
            "date": dates,
            "open": opens,
            "high": [max(o, c) + 0.01 for o, c in zip(opens, closes)],
            "low": [min(o, c) - 0.01 for o, c in zip(opens, closes)],
            "close": closes,
            "volume": [1000] * len(dates),
            "amount": [c * 1000 for c in closes],
        }
    )


def _signal(symbol: str = "600000", d: date = D0) -> Signal:
    return Signal(symbol=symbol, strategy="b1b2b3", signal_type="b1", score=1.0, triggered_at=d)


def _config(**portfolio_overrides) -> BacktestConfig:
    """默认配置 + 组合参数覆盖（止盈止损调到极端，避免干扰）。"""
    cfg = BacktestConfig()
    cfg.portfolio.max_holding_days = 1
    cfg.portfolio.stop_loss_pct = -0.5
    cfg.portfolio.take_profit_pct = 0.5
    for k, v in portfolio_overrides.items():
        setattr(cfg.portfolio, k, v)
    return cfg


def test_portfolio_basic_round_trip():
    """单一信号：T 日收盘触发 → T+1 开盘买入 → T+2 收盘卖出（T+1 约束）。"""
    candles = {"600000": _df([D0, D1, D2, D3], [100, 101, 102, 103], [100, 101, 102, 103])}
    report = simulate_portfolio([_signal()], candles, _config())

    assert report["filled_buys"] == 1
    assert report["trade_count"] == 1
    assert report["open_positions"] == 0
    # 净值曲线覆盖 D0~D3 共 4 个交易日
    assert len(report["equity_curve"]) == 4
    # 盈利（101 买入 → 102 卖出，扣成本后仍为正）
    assert report["total_return"] > 0


def test_portfolio_limit_up_skip_buy():
    """开盘一字涨停：买不进，跳过该信号。"""
    # D0 收盘 10，D1 开盘 11（主板涨停价），无法成交
    candles = {"600000": _df([D0, D1, D2, D3], [10, 11, 11, 11], [10, 11, 11, 11])}
    report = simulate_portfolio([_signal()], candles, _config())

    assert report["filled_buys"] == 0
    assert report["skipped_buys"] == 1
    assert report["trade_count"] == 0


def test_portfolio_limit_down_block_sell():
    """连续跌停卖不出：持仓无法平仓，保留到期末。"""
    # D0 收 10 → D1 开 10 买入，D1 收 9（跌停）；D2 收 8.1（再跌停）；D3 收 7.29（再跌停）
    candles = {
        "600000": _df(
            [D0, D1, D2, D3],
            [10.0, 10.0, 9.0, 8.1],
            [10.0, 9.0, 8.1, 7.29],
        )
    }
    report = simulate_portfolio([_signal()], candles, _config())

    assert report["filled_buys"] == 1
    assert report["trade_count"] == 0  # 一直卖不出去
    assert report["open_positions"] == 1  # 持仓被套到期末


def test_portfolio_cost_reduces_return():
    """有成本时净值低于无成本（同方向）——成本确实在扣。"""
    candles = {"600000": _df([D0, D1, D2, D3], [100, 101, 102, 103], [100, 101, 102, 103])}

    with_cost = _config()
    no_cost = _config()
    no_cost.cost.commission_rate = 0.0
    no_cost.cost.min_commission = 0.0
    no_cost.cost.stamp_tax_rate = 0.0
    no_cost.cost.transfer_fee_rate = 0.0
    no_cost.cost.slippage = 0.0

    r_cost = simulate_portfolio([_signal()], candles, with_cost)
    r_free = simulate_portfolio([_signal()], candles, no_cost)

    assert r_cost["total_return"] < r_free["total_return"]


def test_portfolio_empty_signals():
    report = simulate_portfolio([], {}, _config())
    assert report["equity_curve"] == []
    assert report["total_return"] == 0.0
    assert report["filled_buys"] == 0


def test_strategy_shares_equal_when_none():
    assert _strategy_shares(None, {"a", "b"}) == {"a": 0.5, "b": 0.5}
    assert _strategy_shares({}, {"a", "b"}) == {"a": 0.5, "b": 0.5}
    assert _strategy_shares(None, set()) == {}


def test_strategy_shares_normalizes_and_excludes():
    weights = {"stealth_rally": 6.8, "double_bottom": 3.2, "pin30": 0.0}
    shares = _strategy_shares(weights, {"stealth_rally", "double_bottom", "pin30"})
    assert shares["stealth_rally"] == pytest.approx(6.8 / 10.0)
    assert shares["double_bottom"] == pytest.approx(3.2 / 10.0)
    assert shares["pin30"] == 0.0


def test_eligible_strategies_filters_zero_weight():
    signals = [
        Signal(symbol="600000", strategy="b1b2b3", signal_type="b1", score=1.0, triggered_at=D0),
        Signal(symbol="600001", strategy="stealth_rally", signal_type="x", score=1.0, triggered_at=D0),
    ]
    assert _eligible_strategies(signals, None) == {"b1b2b3", "stealth_rally"}
    assert _eligible_strategies(signals, {"b1b2b3": 0.0, "stealth_rally": 1.0}) == {
        "stealth_rally"
    }


def test_portfolio_weight_zero_strategy_not_bought():
    """权重为 0 的策略信号不建仓。"""
    candles = {"600000": _df([D0, D1, D2, D3], [100, 101, 102, 103], [100, 101, 102, 103])}
    cfg = _config()
    cfg.portfolio.strategy_weights = {"b1b2b3": 0.0, "stealth_rally": 1.0}
    report = simulate_portfolio(
        [Signal(symbol="600000", strategy="b1b2b3", signal_type="b1", score=1.0, triggered_at=D0)],
        candles,
        cfg,
    )
    assert report["filled_buys"] == 0  # b1b2b3 权重 0，不建仓
    assert report["trade_count"] == 0


def test_portfolio_equal_weight_strategy_pools_not_fifo():
    """等权时各策略分池：信号多的策略不能占满所有仓位槽（阶段 8 FIFO 修复）。"""
    symbols_a = ["600001", "600002", "600003"]
    symbol_b = "600004"
    candles = {
        sym: _df([D0, D1, D2, D3], [100, 101, 102, 103], [100, 101, 102, 103])
        for sym in symbols_a + [symbol_b]
    }
    signals = [
        Signal(symbol=sym, strategy="strat_a", signal_type="x", score=float(i), triggered_at=D0)
        for i, sym in enumerate(symbols_a)
    ] + [
        Signal(symbol=symbol_b, strategy="strat_b", signal_type="x", score=9.0, triggered_at=D0)
    ]
    report = simulate_portfolio(signals, candles, _config())
    # 等权两策略各拿 50% 资金池：strat_a 建 2 笔（2×20%）、strat_b 建 1 笔
    # 旧 FIFO 下 strat_a 会占满 4 个仓位槽，strat_b 0 笔
    assert report["filled_buys"] == 3


def test_build_buy_groups_sorts_by_score_and_dedupes():
    """策略内按 score 降序；同标的多信号去重保留 score 高者。"""
    signals = [
        Signal(symbol="600000", strategy="s", signal_type="x", score=1.0, triggered_at=D0),
        Signal(symbol="600001", strategy="s", signal_type="x", score=9.0, triggered_at=D0),
        Signal(symbol="600000", strategy="s", signal_type="x", score=5.0, triggered_at=D0),
    ]
    ord_map = {D1: 0, D2: 1, D3: 2}
    groups = _build_buy_groups(signals, None, ord_map)
    lst = groups[D1]["s"]
    # 600001 score 9 优先；600000 两条信号去重保留 score 5
    assert [s.symbol for s in lst] == ["600001", "600000"]
    assert [s.score for s in lst] == [9.0, 5.0]
