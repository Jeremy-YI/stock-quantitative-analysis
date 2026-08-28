"""回测统计指标单元测试。"""

from __future__ import annotations

import pytest

from backtest.stats import (
    equity_curve,
    max_drawdown,
    profit_loss_ratio,
    quantile,
    sharpe_ratio,
    summarize_returns,
    total_return,
    win_rate,
)


def test_win_rate():
    assert win_rate([]) == 0.0
    assert win_rate([0.01, -0.02, 0.03]) == pytest.approx(2 / 3, abs=1e-9)
    # 0 不算正收益
    assert win_rate([0.0]) == 0.0


def test_profit_loss_ratio():
    # 盈利样本 +10%, +20%；亏损 -10% → 平均盈利 15% / 平均亏损 10% = 1.5
    assert profit_loss_ratio([0.10, 0.20, -0.10]) == pytest.approx(1.5, abs=1e-9)
    # 无亏损 → None
    assert profit_loss_ratio([0.10, 0.20]) is None
    # 无盈利 → None
    assert profit_loss_ratio([-0.10]) is None


def test_quantile_interpolation():
    sv = [0.0, 1.0, 2.0, 3.0]
    assert quantile(sv, 0.0) == 0.0
    assert quantile(sv, 0.5) == 1.5
    assert quantile(sv, 1.0) == 3.0


def test_summarize_returns_empty():
    s = summarize_returns([])
    assert s.n == 0
    assert s.win_rate == 0.0


def test_summarize_returns_basic():
    s = summarize_returns([0.10, -0.10, 0.20])
    assert s.n == 3
    assert s.win_rate == pytest.approx(2 / 3, abs=1e-9)
    assert s.avg_return == pytest.approx((0.10 - 0.10 + 0.20) / 3, abs=1e-9)
    assert s.median_return == pytest.approx(0.10, abs=1e-9)
    assert s.best == 0.20
    assert s.worst == -0.10
    assert set(s.quantiles.keys()) == {"p05", "p25", "p50", "p75", "p95"}


def test_equity_curve():
    assert equity_curve([0.1, -0.1], initial=1.0) == pytest.approx([1.0, 1.1, 0.99], abs=1e-9)


def test_max_drawdown():
    # 先涨 100% 再跌 50%：回撤 50%
    eq = [1.0, 2.0, 1.0]
    assert max_drawdown(eq) == pytest.approx(-0.5, abs=1e-9)
    assert max_drawdown([]) == 0.0
    assert max_drawdown([1.0]) == 0.0


def test_sharpe_ratio():
    assert sharpe_ratio([0.01]) is None  # 样本不足
    assert sharpe_ratio([0.01, 0.01, 0.01]) is None  # 波动为 0
    # 正收益样本 → 夏普 > 0
    assert sharpe_ratio([0.01, 0.02, 0.015]) > 0


def test_total_return():
    assert total_return([1.0, 1.5]) == pytest.approx(0.5, abs=1e-9)
    assert total_return([]) == 0.0
