"""MACD 指标单元测试：黄金值 + 边界情况。"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from indicators.macd import calc_ema, calc_macd

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _load_rows(filename: str) -> list[dict]:
    with (FIXTURES / filename).open(newline="") as f:
        return list(csv.DictReader(f))


def test_golden_values_match_committed_fixture():
    """用真实 600519 切片算 MACD，逐点比对预先算好的黄金值（精确到 4 位小数）。"""
    daily = _load_rows("600519_daily.csv")
    golden = _load_rows("600519_macd_golden.csv")
    closes = [float(row["close"]) for row in daily]

    result = calc_macd(closes)

    assert len(daily) == len(golden)
    assert len(result.dif) == len(closes)
    assert len(result.dea) == len(closes)
    assert len(result.macd) == len(closes)

    for i, expected in enumerate(golden):
        assert result.dif[i] == pytest.approx(float(expected["dif"]), abs=5e-5)
        assert result.dea[i] == pytest.approx(float(expected["dea"]), abs=5e-5)
        assert result.macd[i] == pytest.approx(float(expected["macd"]), abs=5e-5)


def test_empty_input_returns_empty_series():
    result = calc_macd([])
    assert result == ([], [], [])


def test_insufficient_bars_still_returns_full_length_series():
    """不足 26 根 K 线时不崩溃，且输出与输入等长。"""
    closes = [10.0, 10.5, 10.2, 10.8, 11.0]
    result = calc_macd(closes)
    assert len(result.dif) == 5
    assert len(result.dea) == 5
    assert len(result.macd) == 5
    # 首根因 EMA 首值种子，DIF/DEA/MACD 均为 0
    assert result.dif[0] == 0.0
    assert result.dea[0] == 0.0
    assert result.macd[0] == 0.0


def test_trading_halt_gap_produces_finite_values():
    """含停牌跳空缺口的价格序列，指标仍是有限值（不出现 NaN/Inf）。"""
    closes = [10.0] * 10 + [8.0] * 10 + [9.5] * 10
    result = calc_macd(closes)
    assert all(math.isfinite(v) for v in result.dif)
    assert all(math.isfinite(v) for v in result.dea)
    assert all(math.isfinite(v) for v in result.macd)


def test_calc_ema_known_values():
    """手算校验 EMA(3)：k=0.5，ema=[1, 1.5, 2.25]。"""
    assert calc_ema([1.0, 2.0, 3.0], 3) == pytest.approx([1.0, 1.5, 2.25])


def test_calc_ema_rejects_nonpositive_period():
    with pytest.raises(ValueError):
        calc_ema([1.0, 2.0], 0)
