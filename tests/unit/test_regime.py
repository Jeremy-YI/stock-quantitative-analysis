"""市场环境（regime）模块单元测试。"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from market.regime import (
    REGIME_PROFILES,
    classify_regime,
    compute_market_series,
    profile_params,
    should_allow,
    snapshot_at,
)
from tests.helpers import make_candle_df


def _growth_candles(n: int = 130, g: float = 0.005, n_symbols: int = 3) -> dict:
    """构造 n 根、日收益恒为 g 的合成日线（volume 恒定 → activity=1）。"""
    closes = [10.0 * (1.0 + g) ** i for i in range(n)]
    return {
        f"{600000 + i:06d}": make_candle_df(closes, volume=1000.0)
        for i in range(n_symbols)
    }


def test_compute_market_series_up_trend():
    """单调上涨序列：r20 > 0、activity ≈ 1、drawdown ≈ 0。"""
    series = compute_market_series(_growth_candles(), min_symbols=2)

    assert not series.empty
    last = series.iloc[-1]
    # 等权指数日收益恒为 g，20 日涨跌 = (1+g)^20 - 1
    assert last["r20"] == pytest.approx((1.005) ** 20 - 1.0, rel=1e-6)
    assert last["activity"] == pytest.approx(1.0, rel=1e-6)
    assert last["drawdown"] == pytest.approx(0.0, abs=1e-9)


def test_compute_market_series_drawdown_after_fall():
    """先涨后跌：drawdown 应为负（低于 120 日高点）。"""
    n = 130
    closes = [10.0 * (1.01) ** i for i in range(n - 20)]
    closes += [closes[-1] * (0.98) ** i for i in range(1, 21)]
    candles = {f"{600000:06d}": make_candle_df(closes, volume=1000.0)}
    series = compute_market_series(candles, min_symbols=1)

    assert not series.empty
    assert series.iloc[-1]["drawdown"] < -0.01


def test_classify_regime_bins():
    labels = classify_regime(-0.15, 0.5, -0.20)
    assert labels == {
        "index_20d": "强跌<-10%",
        "activity": "清淡<0.8",
        "drawdown": "中跌-25~-15%",
    }

    labels = classify_regime(0.05, 1.3, -0.01)
    assert labels == {
        "index_20d": "上涨4~10%",
        "activity": "活跃1.2-1.5",
        "drawdown": "新高区-3~0",
    }

    # None / NaN → 无数据
    assert classify_regime(None, None, None)["index_20d"] == "无数据"
    assert classify_regime(float("nan"), 1.0, 0.0)["activity"] == "正常1.0-1.2"


def test_should_allow_default_filter():
    # 默认 filter：r20 < +4%、activity < 1.2、-15% ≤ dd ≤ 0
    assert should_allow(0.0, 1.0, -0.05) is True
    assert should_allow(0.05, 1.0, -0.05) is False  # 大盘涨幅过高
    assert should_allow(0.0, 1.3, -0.05) is False  # 活跃度过高
    assert should_allow(0.0, 1.0, -0.20) is False  # 回撤过深
    assert should_allow(0.0, 1.0, 0.02) is False  # 回撤为正（超新高，默认不允许）
    # 数据缺失 / NaN 保守不允许
    assert should_allow(None, 1.0, -0.05) is False
    assert should_allow(0.0, float("nan"), -0.05) is False


def test_snapshot_at_missing_returns_none():
    series = compute_market_series(_growth_candles(), min_symbols=2)
    valid_day = series.index[60]
    snap = snapshot_at(series, valid_day)
    assert snap is not None
    assert snap.date == valid_day
    assert snap.labels["activity"] == "正常1.0-1.2"

    # 无该日的快照
    assert snapshot_at(series, date(1999, 1, 1)) is None
    assert snapshot_at(pd.DataFrame(), date(2026, 1, 1)) is None


def test_regime_profiles_two_classes():
    """两类 regime 档：均值回归（避开深跌）vs 深跌吸筹（要深回撤）。"""
    mr = REGIME_PROFILES["mean_reversion"]
    da = REGIME_PROFILES["deep_accumulation"]
    # 深跌吸筹的下界远深于均值回归（允许深回撤）
    assert da["min_drawdown"] < mr["min_drawdown"]
    # 深跌吸筹允许更高的涨幅 / 活跃度
    assert da["max_index_20d_return"] > mr["max_index_20d_return"]
    assert da["max_activity"] > mr["max_activity"]


def test_profile_params_none_for_unknown():
    assert profile_params("mean_reversion")["max_activity"] == 1.2
    assert profile_params("deep_accumulation")["min_drawdown"] == -0.40
    assert profile_params("none") is None
    assert profile_params(None) is None
    assert profile_params("unknown") is None


def test_regime_filter_from_profile():
    from backtest.config import RegimeFilterConfig

    f = RegimeFilterConfig.from_profile("deep_accumulation")
    assert f is not None
    # 深跌吸筹档允许 -0.20 回撤开仓（默认均值回归档的 min_drawdown=-0.15 会拒绝）
    assert f.allow(0.0, 1.0, -0.20) is True

    assert RegimeFilterConfig.from_profile("none") is None
    assert RegimeFilterConfig.from_profile(None) is None
