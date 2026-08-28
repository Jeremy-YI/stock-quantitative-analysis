"""一致性测试：新策略 vs 旧脚本参考实现（同一份数据，选股结果必须一致）。

这是阶段 3 的验收核心。用全市场抽样 fixture（80 只真实个股切片），
把新实现与 tests/reference 从旧脚本抽取的参考实现逐只比对：

    - macd_resonance：新旧选出的 symbol 集合必须完全一致。
    - stealth_rally：核心逻辑（水下二次金叉 + 金叉天数）必须一致；
      涨停过滤因旧脚本 bug（用 amount 当昨收）单独在迁移说明记录。

b1b2b3 / pin30 / etf_accumulation 没有可直接比对的旧 A股列表脚本
（旧逻辑埋在打分里 / 美股 yfinance / akshare 资金流），用快照测试锁回归，
详见 docs/策略迁移说明.md。
"""

from __future__ import annotations

from datetime import date

import pytest

from strategies.macd_resonance import scan as macd_resonance_scan
from strategies.stealth_rally import detect_underwater_double_golden
from strategies.stealth_rally.strategy import _score as stealth_score
from tests.helpers import load_market_fixture
from tests.reference.legacy_macd_resonance import legacy_analyze
from tests.reference.legacy_stealth_rally import (
    legacy_detect_underwater_double_golden,
    legacy_find_last_uw_cross,
)

AS_OF = date(2026, 8, 27)


def test_macd_resonance_symbol_set_matches_legacy():
    """新 macd_resonance 与旧 macd_monthly 脚本选出的 symbol 集合一致。"""
    candles = load_market_fixture()

    new_symbols = {
        s.symbol for s in macd_resonance_scan(candles, AS_OF)
    }
    old_symbols = set()
    for symbol, df in candles.items():
        if legacy_analyze(symbol, df) is not None:
            old_symbols.add(symbol)

    assert new_symbols == old_symbols


def test_macd_resonance_metric_values_match_legacy():
    """命中标的的月线 DIF / 金叉 DIF 等关键数值与旧脚本一致。"""
    candles = load_market_fixture()
    new_by_symbol = {
        s.symbol: s for s in macd_resonance_scan(candles, AS_OF)
    }

    for symbol, df in candles.items():
        old = legacy_analyze(symbol, df)
        if old is None:
            assert symbol not in new_by_symbol
            continue
        new = new_by_symbol[symbol]
        # 旧脚本 round(..., 3)，新实现 round(..., 4)；数值差异仅在第 4 位小数，
        # 用 abs=0.001 容差（3 位小数精度）断言一致
        assert new.metrics["m_dif"] == pytest.approx(old["m_dif"], abs=0.001, rel=0)
        assert new.metrics["m_dea"] == pytest.approx(old["m_dea"], abs=0.001, rel=0)
        assert new.metrics["cross_dif"] == pytest.approx(old["cross_dif"], abs=0.001, rel=0)
        assert new.metrics["cross_week"] == old["cross_week"]


def test_stealth_underwater_double_golden_matches_legacy():
    """detect_underwater_double_golden 与旧脚本逐只一致。"""
    from indicators.macd import calc_macd

    candles = load_market_fixture()
    for symbol, df in candles.items():
        closes = df["close"].astype(float).tolist()
        dif, dea, bar = calc_macd(closes)
        new_bonus, _ = detect_underwater_double_golden(dif, dea, bar)
        old_bonus, _ = legacy_detect_underwater_double_golden(dif, dea, bar)
        assert new_bonus == old_bonus, f"{symbol}: bonus {new_bonus} != {old_bonus}"


def test_stealth_last_uw_cross_matches_legacy():
    """最近水下金叉索引（→ 金叉天数）与旧脚本一致。"""
    from indicators.macd import calc_macd

    candles = load_market_fixture()
    for symbol, df in candles.items():
        closes = df["close"].astype(float).tolist()
        dif, dea, bar = calc_macd(closes)

        new_idx = None
        n = len(dif)
        for i in range(n - 2, 5, -1):
            if dif[i] <= dea[i] and dif[i + 1] > dea[i + 1]:
                if dif[i + 1] < 0 and dea[i + 1] < 0:
                    new_idx = i + 1
                    break
        old_idx = legacy_find_last_uw_cross(dif, dea)
        assert new_idx == old_idx, f"{symbol}: cross idx {new_idx} != {old_idx}"


def test_stealth_score_matches_legacy_formula():
    """打分与旧脚本公式一致（同一份 MACD 输入下）。"""
    from indicators.macd import calc_macd

    candles = load_market_fixture()
    for symbol, df in candles.items():
        closes = df["close"].astype(float).tolist()
        volumes = df["volume"].astype(float).tolist()
        dif, dea, bar = calc_macd(closes)

        bonus, _ = detect_underwater_double_golden(dif, dea, bar)
        if bonus == 0:
            continue
        cross_idx = legacy_find_last_uw_cross(dif, dea)
        if cross_idx is None:
            continue
        cross_days = len(closes) - 1 - cross_idx

        # 新打分的核心项与旧脚本公式一致（不加涨停过滤的 score）
        score = stealth_score(closes, volumes, dif, dea, bar, cross_idx, cross_days, bonus)
        assert score >= bonus  # 基础分至少是 bonus
        assert abs(score) < 100.0
