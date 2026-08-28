"""量能指标单元测试：黄金值 + 边界情况。"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from indicators.volume import (
    REL_NO_DATA,
    REL_PRICE_DOWN_VOLUME_DOWN,
    REL_PRICE_DOWN_VOLUME_UP,
    REL_PRICE_UP_VOLUME_DOWN,
    REL_PRICE_UP_VOLUME_UP,
    calc_volume_ma,
    calc_volume_ratio,
    calc_volume_ratio_60,
    classify_price_volume,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _load_daily() -> list[dict]:
    with (FIXTURES / "600519_daily.csv").open(newline="") as f:
        return list(csv.DictReader(f))


def _load_golden(filename: str) -> list[dict]:
    with (FIXTURES / filename).open(newline="") as f:
        return list(csv.DictReader(f))


def test_golden_values_match_committed_fixture():
    """用真实 600519 切片算量能，逐点比对预先算好的黄金值。"""
    daily = _load_daily()
    golden = _load_golden("600519_volume_golden.csv")
    closes = [float(r["close"]) for r in daily]
    volumes = [float(r["volume"]) for r in daily]

    ma = calc_volume_ma(volumes)
    ratio = calc_volume_ratio(volumes)
    relations = classify_price_volume(closes, volumes)

    assert len(daily) == len(golden)
    for i, expected in enumerate(golden):
        assert ma.mavol1[i] == pytest.approx(float(expected["mavol1"]), abs=5e-5)
        assert ma.mavol2[i] == pytest.approx(float(expected["mavol2"]), abs=5e-5)
        assert ratio[i] == pytest.approx(float(expected["volume_ratio"]), abs=5e-5)
        assert relations[i] == expected["relation"]


def test_empty_input_returns_empty_series():
    assert calc_volume_ma([]) == ([], [])
    assert calc_volume_ratio([]) == []
    assert classify_price_volume([], []) == []


def test_volume_ma_warmup_uses_partial_window():
    """窗口不足时用已有数据平均（首根等于当日量本身）。"""
    volumes = [100.0, 200.0, 300.0]
    result = calc_volume_ma(volumes)
    assert result.mavol1 == [100.0, 150.0, 200.0]
    assert result.mavol2 == [100.0, 150.0, 200.0]


def test_volume_ratio_first_bar_is_neutral():
    """首根无前日可比，量比取中性 1.0。"""
    volumes = [100.0, 120.0, 110.0]
    result = calc_volume_ratio(volumes)
    assert result[0] == 1.0


def test_volume_ratio_known_values():
    """第 6 根的量比 = 当日量 / 过去 5 日均量（不含当日）。"""
    volumes = [100.0, 100.0, 100.0, 100.0, 100.0, 200.0]
    result = calc_volume_ratio(volumes)
    assert result[5] == pytest.approx(2.0, abs=1e-9)


def test_zero_volume_is_safe():
    """成交量为 0 时不除零，输出有限值。"""
    volumes = [0.0, 0.0, 0.0]
    ma = calc_volume_ma(volumes)
    ratio = calc_volume_ratio(volumes)
    assert all(math.isfinite(v) for v in ma.mavol1)
    assert all(math.isfinite(v) for v in ratio)


def test_volume_ratio_60_uses_60_day_window():
    """60 日基准量比：当日量 / 过去 60 日均量（不含当日），窗口不足用已有数据。"""
    volumes = [100.0] * 60 + [200.0]
    result = calc_volume_ratio_60(volumes)
    assert result[60] == pytest.approx(2.0, abs=1e-9)
    # 与显式 period=60 的 calc_volume_ratio 一致
    assert result == calc_volume_ratio(volumes, period=60)


def test_volume_ratio_60_empty_and_neutral():
    assert calc_volume_ratio_60([]) == []
    assert calc_volume_ratio_60([10.0]) == [1.0]  # 首根中性


def test_classify_four_quadrants():
    """四象限价量关系判定。"""
    # 构造：MAVOL1 固定约 100，用明显高于/低于均量的量区分放量/缩量
    volumes = [100.0, 100.0, 100.0, 100.0, 100.0, 150.0, 50.0, 150.0, 50.0]
    closes = [10.0, 10.0, 10.0, 10.0, 10.0, 11.0, 12.0, 11.0, 10.0]
    relations = classify_price_volume(closes, volumes)

    assert relations[0] == REL_NO_DATA  # 首根无前日可比
    assert relations[5] == REL_PRICE_UP_VOLUME_UP  # 涨 + 放量
    assert relations[6] == REL_PRICE_UP_VOLUME_DOWN  # 涨 + 缩量
    assert relations[7] == REL_PRICE_DOWN_VOLUME_UP  # 跌 + 放量
    assert relations[8] == REL_PRICE_DOWN_VOLUME_DOWN  # 跌 + 缩量


def test_classify_flat_price():
    """价格不变时判为价平。"""
    volumes = [100.0, 100.0, 100.0]
    closes = [10.0, 10.0, 10.0]
    relations = classify_price_volume(closes, volumes)
    assert relations[1] == "价平"
    assert relations[2] == "价平"


def test_classify_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        classify_price_volume([1.0, 2.0], [100.0])
