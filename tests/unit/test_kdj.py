"""KDJ 指标单元测试：黄金值 + 边界情况。"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from indicators.kdj import calc_kdj

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _load_daily() -> list[dict]:
    with (FIXTURES / "600519_daily.csv").open(newline="") as f:
        return list(csv.DictReader(f))


def _load_golden(filename: str) -> list[dict]:
    with (FIXTURES / filename).open(newline="") as f:
        return list(csv.DictReader(f))


def test_golden_values_match_committed_fixture():
    """用真实 600519 切片算 KDJ，逐点比对预先算好的黄金值（4 位小数）。"""
    daily = _load_daily()
    golden = _load_golden("600519_kdj_golden.csv")
    highs = [float(r["high"]) for r in daily]
    lows = [float(r["low"]) for r in daily]
    closes = [float(r["close"]) for r in daily]

    result = calc_kdj(highs, lows, closes)

    assert len(daily) == len(golden)
    for i, expected in enumerate(golden):
        assert result.k[i] == pytest.approx(float(expected["k"]), abs=5e-5)
        assert result.d[i] == pytest.approx(float(expected["d"]), abs=5e-5)
        assert result.j[i] == pytest.approx(float(expected["j"]), abs=5e-5)


def test_empty_input_returns_empty_series():
    result = calc_kdj([], [], [])
    assert result == ([], [], [])


def test_insufficient_bars_returns_neutral_series():
    """不足 9 根 K 线时全部返回中性值 50，且输出与输入等长。"""
    highs = [10.0, 10.5, 10.2]
    lows = [9.5, 9.8, 9.6]
    closes = [10.0, 10.1, 9.9]
    result = calc_kdj(highs, lows, closes)
    assert len(result.k) == len(result.d) == len(result.j) == 3
    assert result.k == [50.0, 50.0, 50.0]
    assert result.d == [50.0, 50.0, 50.0]
    assert result.j == [50.0, 50.0, 50.0]


def test_warmup_bars_padded_with_neutral():
    """前 8 根无完整窗口，应填充 50，从第 9 根起才有真实值。"""
    n = 9
    highs = [10.0 + i for i in range(n)]
    lows = [9.0 + i for i in range(n)]
    closes = [9.5 + i for i in range(n)]
    result = calc_kdj(highs, lows, closes)
    assert result.k[: n - 1] == [50.0] * (n - 1)
    assert result.k[n - 1] != 50.0


def test_flat_prices_produce_finite_values():
    """全部涨停（最高=最低=收盘，无波动）时 RSV 取 50，指标有限且不除零。"""
    n = 15
    highs = [10.0] * n
    lows = [10.0] * n
    closes = [10.0] * n
    result = calc_kdj(highs, lows, closes)
    assert all(math.isfinite(v) for v in result.k)
    assert all(math.isfinite(v) for v in result.d)
    assert all(math.isfinite(v) for v in result.j)
    # 无波动时 RSV=50，K 会从 50 逐渐收敛到 50
    assert result.k[-1] == pytest.approx(50.0, abs=1e-6)


def test_trading_halt_gap_produces_finite_values():
    """含停牌跳空缺口的序列，指标仍是有限值。"""
    highs = [10.0] * 10 + [9.0] * 10
    lows = [9.0] * 10 + [8.0] * 10
    closes = [9.5] * 10 + [8.5] * 10
    result = calc_kdj(highs, lows, closes)
    assert all(math.isfinite(v) for v in result.k)
    assert all(math.isfinite(v) for v in result.d)
    assert all(math.isfinite(v) for v in result.j)


def test_rejects_nonpositive_period():
    with pytest.raises(ValueError):
        calc_kdj([1.0], [1.0], [1.0], period=0)


def test_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        calc_kdj([1.0, 2.0], [1.0], [1.0, 2.0])


def test_custom_period_is_supported():
    """自定义周期（如 n=3）也能得到等长且有限的结果。"""
    highs = [10.0 + i for i in range(10)]
    lows = [9.0 + i for i in range(10)]
    closes = [9.5 + i for i in range(10)]
    result = calc_kdj(highs, lows, closes, period=3)
    assert len(result.k) == 10
    # 前 period-1 = 2 根填充 50
    assert result.k[:2] == [50.0, 50.0]
    assert all(math.isfinite(v) for v in result.k)
