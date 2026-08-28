"""基线计算单测：已知数据构造，断言基线胜率 / 平均收益 / 当日基线正确。"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from backtest.baseline import (
    compute_baseline,
    daily_baseline_win_rates,
)
from tests.helpers import make_candle_df


def _rising(start: date, n: int = 20, base: float = 10.0) -> pd.DataFrame:
    return make_candle_df([base * (1.01**i) for i in range(n)], start=start)


def _falling(start: date, n: int = 20, base: float = 10.0) -> pd.DataFrame:
    return make_candle_df([base * (0.99**i) for i in range(n)], start=start)


def test_compute_baseline_rising_universe_is_all_win():
    """单边上涨宇宙：基线胜率应为 100%，平均收益 = 单日涨幅。"""
    df = _rising(date(2026, 6, 1), n=20)
    result = compute_baseline(
        {"600000": df}, {"600000"}, "stock", date(2026, 6, 1), date(2026, 6, 15), [1]
    )
    assert result.universe == "stock"
    assert result.size == 1
    h = result.holds[0]
    assert h.hold_days == 1
    assert h.win_rate == pytest.approx(1.0)
    assert h.avg_return == pytest.approx(0.01, abs=1e-9)


def test_compute_baseline_half_up_half_down_win_rate():
    """一只上涨 + 一只下跌：1 日基线胜率应为 50%（等样本近似）。"""
    candles = {
        "600000": _rising(date(2026, 6, 1), n=20),
        "000001": _falling(date(2026, 6, 1), n=20),
    }
    result = compute_baseline(
        candles, {"600000", "000001"}, "stock", date(2026, 6, 1), date(2026, 6, 15), [1]
    )
    h = result.holds[0]
    # 上涨 1 日 +0.01（正），下跌 1 日 -0.01（负）→ 胜率约 50%
    assert h.win_rate == pytest.approx(0.5, abs=0.05)


def test_compute_baseline_hold_days_shift():
    """持有 3 日：上涨宇宙平均收益 ≈ 3 日复利。"""
    df = _rising(date(2026, 6, 1), n=20)
    result = compute_baseline(
        {"600000": df}, {"600000"}, "stock", date(2026, 6, 1), date(2026, 6, 15), [3]
    )
    h = result.holds[0]
    assert h.avg_return == pytest.approx(1.01**3 - 1, abs=1e-6)


def test_compute_baseline_empty_universe():
    result = compute_baseline({}, set(), "stock", date(2026, 6, 1), date(2026, 6, 15), [1])
    assert result.size == 0
    assert result.holds[0].n == 0
    assert result.holds[0].win_rate == 0.0


def test_daily_baseline_win_rates_per_day():
    """当日基线：上涨标的每一天都是 1.0，下跌标的是 0.0。"""
    candles = {
        "600000": _rising(date(2026, 6, 1), n=20),
        "000001": _falling(date(2026, 6, 1), n=20),
    }
    daily = daily_baseline_win_rates(
        candles, {"600000", "000001"}, date(2026, 6, 1), date(2026, 6, 15), [1]
    )
    day = date(2026, 6, 10)
    # 两只标的各算一天 → 一涨一跌 → 当日基线 50%
    assert day in daily[1]
    assert daily[1][day] == pytest.approx(0.5)
