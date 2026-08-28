"""因子研究模块单元测试：纯函数（超额计算 / 交叉 / 分层）+ 数据集构建。"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from research.dataset import MAS, build_factor_dataset
from research.factors import cross_excess, excess_boolean, excess_by_bins
from research.regime import layered_excess
from tests.helpers import make_candle_df


def test_mas_are_jeremy_real_params():
    assert MAS == (5, 13, 25, 75, 120)


# ---------------------------------------------------------------------------
# 纯函数：超额计算
# ---------------------------------------------------------------------------
def _bin_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "x": [0.1, 0.2, 0.9, 1.0],
            "ret": [0.1, 0.2, -0.1, -0.2],
        }
    )


def test_excess_by_bins():
    frame = _bin_frame()
    g = excess_by_bins(frame, "x", [0.0, 0.5, 2.0], ["low", "high"])
    low = g[g["label"] == "low"].iloc[0]
    high = g[g["label"] == "high"].iloc[0]

    assert low["n"] == 2
    assert low["win_rate"] == pytest.approx(1.0)
    assert low["excess_win_rate"] == pytest.approx(0.5)  # 基线 0.5
    assert high["win_rate"] == pytest.approx(0.0)
    assert high["excess_win_rate"] == pytest.approx(-0.5)


def test_excess_by_bins_respects_explicit_baseline():
    frame = _bin_frame()
    g = excess_by_bins(frame, "x", [0.0, 0.5, 2.0], ["low", "high"], baseline=0.0)
    low = g[g["label"] == "low"].iloc[0]
    assert low["excess_win_rate"] == pytest.approx(1.0)  # 基线 0 → 超额 = 胜率本身


def test_excess_boolean():
    frame = _bin_frame()
    r = excess_boolean(frame, np.array([True, True, False, False]), "top2")
    assert r["n"] == 2
    assert r["win_rate"] == pytest.approx(1.0)
    assert r["excess_win_rate"] == pytest.approx(0.5)


def test_cross_excess_shape():
    frame = pd.DataFrame(
        {
            "a": [0.1, 0.1, 0.9, 0.9, 0.1, 0.9],
            "b": [0.2, 0.8, 0.2, 0.8, 0.2, 0.8],
            "ret": [0.1, -0.1, 0.2, -0.2, 0.05, -0.05],
        }
    )
    g = cross_excess(
        frame, "a", [0, 0.5, 2.0], ["aLo", "aHi"], "b", [0, 0.5, 2.0], ["bLo", "bHi"]
    )
    assert set(g.columns) >= {"row", "col", "n", "win_rate", "excess_win_rate"}
    assert len(g) == 4  # 2×2 全有样本
    assert g["n"].sum() == 6


def test_layered_excess():
    n = 400
    rng = np.random.default_rng(0)
    frame = pd.DataFrame(
        {
            "regime": rng.uniform(-0.2, 0.2, n),
            "ret": rng.normal(0.0, 0.1, n),
            "trend": rng.random(n) < 0.4,
            "rev": rng.random(n) < 0.4,
        }
    )
    trend = frame["trend"].to_numpy()
    rev = frame["rev"].to_numpy()
    out = layered_excess(
        frame,
        "regime",
        [-0.2, -0.05, 0.05, 0.2],
        ["跌", "平", "涨"],
        trend,
        rev,
    )
    assert set(out.columns) >= {
        "label",
        "baseline_win_rate",
        "trend_n",
        "trend_excess",
        "reversion_n",
        "reversion_excess",
    }
    assert len(out) == 3
    # 每个档位基线胜率在 [0,1]
    assert out["baseline_win_rate"].between(0.0, 1.0).all()


# ---------------------------------------------------------------------------
# 数据集构建
# ---------------------------------------------------------------------------
def _candles() -> dict:
    """3 只 140 根的合成标的（涨 / 跌 / 震荡）。"""
    rising = [10.0 * (1.01**i) for i in range(140)]
    falling = [50.0 * (0.99**i) for i in range(140)]
    choppy = [20.0 + (0.5 if i % 2 == 0 else -0.5) for i in range(140)]
    return {
        "600001": make_candle_df(rising, start=date(2026, 1, 2)),
        "600002": make_candle_df(falling, start=date(2026, 1, 2)),
        "600003": make_candle_df(choppy, start=date(2026, 1, 2)),
    }


def test_build_factor_dataset_columns_and_ret():
    frame = build_factor_dataset(
        _candles(), date(2026, 5, 1), date(2026, 6, 30), hold_days=5
    )
    assert not frame.empty
    for col in ("vr5", "vr20", "vr60", "dif", "dea", "above", "gold", "cross",
                "below_bull", "perfect", "short_bull", "above120", "mid_bull",
                "dev5", "ret", "date", "symbol"):
        assert col in frame.columns, f"缺少列 {col}"
    # ret 无 NaN
    assert frame["ret"].notna().all()


def test_build_factor_dataset_empty_when_too_few_bars():
    short = {"600001": make_candle_df([10.0 * (1.01**i) for i in range(40)])}
    frame = build_factor_dataset(short, date(2026, 1, 1), date(2026, 6, 30), hold_days=5)
    assert frame.empty
