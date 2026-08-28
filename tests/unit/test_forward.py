"""前向收益计算单元测试（含数据末尾不足 / 信号日缺失 / 停牌跨越边界）。"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from backtest.forward import forward_return_series, forward_returns
from tests.helpers import make_candle_df


def _df(closes: list[float], start: date = date(2026, 8, 24)) -> pd.DataFrame:
    return make_candle_df(closes, start=start)


def test_forward_returns_basic():
    # 收盘价单调 +10%/根（用 1.1 倍递增），信号在首根
    closes = [100.0 * (1.1**i) for i in range(6)]
    df = _df(closes)
    signal_date = df["date"].iloc[0]
    fr = forward_returns(df, signal_date, [1, 2, 3])
    assert fr[1] == pytest.approx(0.1, abs=1e-9)  # 110/100 - 1
    assert fr[2] == pytest.approx(0.21, abs=1e-9)  # 121/100 - 1
    assert fr[3] == pytest.approx(0.331, abs=1e-9)  # 133.1/100 - 1


def test_forward_returns_end_of_data_returns_none():
    closes = [100.0, 101.0, 102.0]  # 仅 3 根
    df = _df(closes)
    signal_date = df["date"].iloc[0]
    fr = forward_returns(df, signal_date, [1, 2, 5])
    assert fr[1] is not None
    assert fr[2] is not None  # 102/100 - 1
    assert fr[5] is None  # 数据末尾不足 5 日 → None


def test_forward_returns_missing_signal_date():
    closes = [100.0, 101.0, 102.0]
    df = _df(closes)
    # 一个不在 df 里的日期
    fr = forward_returns(df, date(2026, 8, 31), [1, 3])
    assert fr == {1: None, 3: None}


def test_forward_returns_suspension_skips():
    # 构造停牌：直接手写 df，跳过中间某交易日（模拟停牌无 K 线）
    df = pd.DataFrame(
        {
            "date": [date(2026, 8, 24), date(2026, 8, 25), date(2026, 8, 27)],
            "open": [100.0, 100.0, 105.0],
            "high": [101.0, 101.0, 106.0],
            "low": [99.0, 99.0, 104.0],
            "close": [100.0, 101.0, 105.0],
            "volume": [1000, 1000, 1000],
            "amount": [100000, 101000, 105000],
        }
    )
    # 08-26 停牌（无 K 线），持有 2 日跨过停牌 → 08-27 收盘 105/100 - 1 = 5%
    fr = forward_returns(df, date(2026, 8, 24), [2])
    assert fr[2] == pytest.approx(0.05, abs=1e-9)


def test_forward_return_series_convenience():
    df = _df([100.0, 110.0])
    signal_date = df["date"].iloc[0]
    assert forward_return_series(df, signal_date, 1) == pytest.approx(0.1, abs=1e-9)
