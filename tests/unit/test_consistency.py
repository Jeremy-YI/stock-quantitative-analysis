"""一致性测试：新实现 vs 旧脚本参考实现（数值必须 1e-6 内一致）。

这是本阶段最关键的一环——迁移后策略结果不能变。用同一份 600519 fixture，
分别跑 packages/indicators 的新实现与 tests/reference 抽取的旧实现，逐点比对。
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from indicators.kdj import calc_kdj
from indicators.rsi import calc_rsi
from indicators.volume import calc_volume_ma, calc_volume_ratio
from tests.reference.legacy_indicators import (
    legacy_calc_kdj,
    legacy_calc_rsi,
    legacy_ma,
    legacy_volume_ratio_last,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _load_ohlcv() -> tuple[list[float], list[float], list[float], list[float]]:
    with (FIXTURES / "600519_daily.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    return (
        [float(r["high"]) for r in rows],
        [float(r["low"]) for r in rows],
        [float(r["close"]) for r in rows],
        [float(r["volume"]) for r in rows],
    )


def _assert_series_equal(new: list[float], legacy: list[float]) -> None:
    assert len(new) == len(legacy)
    for a, b in zip(new, legacy):
        assert a == pytest.approx(b, abs=1e-6)


def test_kdj_matches_legacy_reference():
    """新 calc_kdj 与 daily_stock_picker.py 参考实现逐点一致。"""
    highs, lows, closes, _ = _load_ohlcv()

    new_k, new_d, new_j = calc_kdj(highs, lows, closes)
    old_k, old_d, old_j = legacy_calc_kdj(highs, lows, closes)

    _assert_series_equal(new_k, old_k)
    _assert_series_equal(new_d, old_d)
    _assert_series_equal(new_j, old_j)


def test_rsi_matches_legacy_reference():
    """新 calc_rsi 与 daily_stock_picker.py 参考实现逐点一致（真实数据不触发平盘特例）。"""
    _, _, closes, _ = _load_ohlcv()

    new_rsi = calc_rsi(closes)
    old_rsi = legacy_calc_rsi(closes)

    _assert_series_equal(new_rsi, old_rsi)


def test_volume_ma_matches_legacy_reference():
    """新 calc_volume_ma 与 kdj_b1_backtest_all.py 的 ma(v,5)/ma(v,10) 一致。"""
    _, _, _, volumes = _load_ohlcv()

    new = calc_volume_ma(volumes)
    old_mavol1 = legacy_ma(volumes, 5)
    old_mavol2 = legacy_ma(volumes, 10)

    _assert_series_equal(new.mavol1, old_mavol1)
    _assert_series_equal(new.mavol2, old_mavol2)


def test_volume_ratio_last_matches_legacy_reference():
    """新 calc_volume_ratio 的最后一根与 daily_stock_picker.py 的 vr 一致。"""
    _, _, _, volumes = _load_ohlcv()

    new_last = calc_volume_ratio(volumes)[-1]
    old_last = legacy_volume_ratio_last(volumes)

    assert new_last == pytest.approx(old_last, abs=1e-6)
    assert math.isfinite(new_last)
