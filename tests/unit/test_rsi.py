"""RSI 指标单元测试：黄金值 + 边界情况。"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from indicators.rsi import calc_rsi

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _load_daily() -> list[dict]:
    with (FIXTURES / "600519_daily.csv").open(newline="") as f:
        return list(csv.DictReader(f))


def _load_golden(filename: str) -> list[dict]:
    with (FIXTURES / filename).open(newline="") as f:
        return list(csv.DictReader(f))


def test_golden_values_match_committed_fixture():
    """用真实 600519 切片算 RSI，逐点比对预先算好的黄金值（4 位小数）。"""
    daily = _load_daily()
    golden = _load_golden("600519_rsi_golden.csv")
    closes = [float(r["close"]) for r in daily]

    result = calc_rsi(closes)

    assert len(daily) == len(golden) == len(result)
    for i, expected in enumerate(golden):
        assert result[i] == pytest.approx(float(expected["rsi"]), abs=5e-5)


def test_empty_input_returns_empty_series():
    assert calc_rsi([]) == []


def test_insufficient_bars_returns_neutral_series():
    """不足 15 根（period+1）K 线时返回全中性值 50。"""
    closes = [10.0, 10.5, 10.2, 10.8]
    result = calc_rsi(closes)
    assert result == [50.0, 50.0, 50.0, 50.0]


def test_warmup_bars_padded_with_neutral():
    """前 14 根无 RSI，填充 50；第 15 根起才有真实值。"""
    closes = [10.0 + i * 0.1 for i in range(20)]
    result = calc_rsi(closes)
    assert result[:14] == [50.0] * 14
    assert result[14] != 50.0


def test_monotonic_rise_reaches_full_strength():
    """连续上涨（无下跌）→ RSI = 100（超买极值）。"""
    closes = [10.0 + i for i in range(30)]
    result = calc_rsi(closes)
    assert result[-1] == pytest.approx(100.0, abs=1e-9)


def test_monotonic_fall_reaches_zero():
    """连续下跌（无上涨）→ RSI = 0（超卖极值）。"""
    closes = [100.0 - i for i in range(30)]
    result = calc_rsi(closes)
    assert result[-1] == pytest.approx(0.0, abs=1e-9)


def test_flat_prices_return_neutral():
    """全部涨停（无波动）→ RSI = 50（中性，标准定义，修正旧脚本返回 100 的问题）。"""
    closes = [10.0] * 30
    result = calc_rsi(closes)
    assert result[-1] == pytest.approx(50.0, abs=1e-9)
    assert result[:14] == [50.0] * 14


def test_trading_halt_gap_produces_finite_values():
    """含停牌跳空缺口的序列，指标仍是有限值。"""
    closes = [10.0] * 10 + [8.0] * 10 + [9.5] * 10
    result = calc_rsi(closes)
    assert all(math.isfinite(v) for v in result)
    assert all(0.0 <= v <= 100.0 for v in result)


def test_rejects_nonpositive_period():
    with pytest.raises(ValueError):
        calc_rsi([1.0, 2.0], period=0)


def test_custom_period_is_supported():
    """自定义周期（如 n=5）也能得到等长且有限的结果。"""
    closes = [10.0 + (i % 3) for i in range(20)]
    result = calc_rsi(closes, period=5)
    assert len(result) == 20
    assert result[:5] == [50.0] * 5
    assert all(0.0 <= v <= 100.0 for v in result)
