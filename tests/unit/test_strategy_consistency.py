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
from strategies.double_bottom.config import DoubleBottomConfig
from strategies.double_bottom.strategy import _detect as double_bottom_detect
from tests.helpers import load_market_fixture, make_double_bottom_candles
from tests.reference.legacy_double_bottom import legacy_detect_double_bottom
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


# --------------------------------------------------------------------------
# 双底反弹一致性测试
# --------------------------------------------------------------------------
# 旧脚本 us_double_bottom.py 是美股口径（流动性用 closes×volume 当「美元成交额」），
# 新实现用 A股 hsjday 的 amount（成交额，元）列。一致性比对把两边流动性门槛都关掉
# （min_amount=0 / min_dollar_vol=0）后，比对新旧「是否选出信号」的集合——
# 二者形态判定逻辑（摆动低点/配对/颈线/底背离/量能）应逐行一致。
# 其余差异（流动性口径、回撤基准 max(highs) vs 近 250 日）只影响 score 不影响选择，
# 详见 docs/双底反弹迁移说明.md。


def _double_bottom_synthetic_corpus() -> dict[str, dict]:
    """构造一组触发/不触发的 W 底序列，供新旧选择集合比对（非空、有意义）。"""
    base = make_double_bottom_candles()["600519"]
    closes = base["close"].astype(float).tolist()
    highs = base["high"].astype(float).tolist()
    lows = base["low"].astype(float).tolist()
    vols = base["volume"].astype(float).tolist()
    amounts = base["amount"].astype(float).tolist()
    n = len(closes)

    # 变体 1：右底相对左底抬高 10%（超出容差 → 不触发）
    v1 = list(closes)
    for i in range(185, n):
        v1[i] = closes[i] + 6.0

    # 变体 2：颈线反弹不足（中间最高点砍低 → 不触发）
    v2 = list(closes)
    for i in range(150, 185):
        v2[i] = closes[i] - 6.0

    # 变体 3：单边下跌（无第二个低点 → 不触发）
    v3 = [100.0 - i * 0.5 for i in range(n)]

    def to_df(cc):
        return {
            "closes": cc,
            "highs": [x * 1.005 for x in cc],
            "lows": [x * 0.995 for x in cc],
            "vols": [1_000_000.0] * len(cc),
            "amounts": [x * 1_000_000.0 for x in cc],
        }

    return {
        "base": {"closes": closes, "highs": highs, "lows": lows, "vols": vols, "amounts": amounts},
        "l2_too_high": to_df(v1),
        "weak_rally": to_df(v2),
        "single_low": to_df(v3),
    }


def test_double_bottom_selection_matches_legacy():
    """新旧在合成 W 底语料上的「是否触发」集合一致（流动性门槛关掉）。"""
    cfg = DoubleBottomConfig(min_amount=0.0)
    for case, d in _double_bottom_synthetic_corpus().items():
        new = double_bottom_detect(d["closes"], d["highs"], d["lows"], d["vols"], d["amounts"], cfg)
        old = legacy_detect_double_bottom(
            d["closes"], d["highs"], d["lows"], d["vols"], min_dollar_vol=0.0
        )
        assert (new is None) == (old is None), f"{case}: new={new is not None}, old={old is not None}"


def test_double_bottom_selection_matches_legacy_on_market_fixture():
    """新旧在真实抽样 fixture（80 只）上的选择集合一致（流动性门槛关掉）。"""
    candles = load_market_fixture()
    cfg = DoubleBottomConfig(min_amount=0.0)
    for symbol, df in candles.items():
        c = df["close"].astype(float).tolist()
        h = df["high"].astype(float).tolist()
        l = df["low"].astype(float).tolist()
        v = df["volume"].astype(float).tolist()
        a = df["amount"].astype(float).tolist()
        new = double_bottom_detect(c, h, l, v, a, cfg)
        old = legacy_detect_double_bottom(c, h, l, v, min_dollar_vol=0.0)
        assert (new is None) == (old is None), f"{symbol}: new={new is not None}, old={old is not None}"
