"""推荐风控过滤：放量长上影 / 放量阴线 / 追高。

这三条在 docs/样本外验证报告.md 里是四段一致的稳健结论（放量必差、追高必差），
所以作为硬过滤器写死。反面案例来自 Jeremy 2026-08-31 提的 002961 瑞达期货。
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from services.strategy_rating_service import risk_reasons


def _frame(rows: list[dict], as_of: date) -> pd.DataFrame:
    """rows 从旧到新，最后一行的日期是 as_of。"""
    days = [as_of - timedelta(days=len(rows) - 1 - i) for i in range(len(rows))]
    return pd.DataFrame([{**r, "date": d} for r, d in zip(rows, days)])


def _bar(o: float, h: float, l: float, c: float, v: float) -> dict:
    return {"open": o, "high": h, "low": l, "close": c, "volume": v, "amount": 0.0}


AS_OF = date(2026, 8, 28)


def test_passes_clean_bar():
    df = _frame([_bar(10, 10.2, 9.9, 10.1, 10000)] * 12, AS_OF)
    assert risk_reasons(df, AS_OF) == []


def test_flags_volume_upper_shadow_002961():
    """002961 真实数据：上影占 51%、量比 3.0、阴线 → 必须拦下。"""
    df = _frame(
        [
            _bar(18.36, 18.67, 18.12, 18.63, 38727),
            _bar(18.63, 18.93, 18.33, 18.51, 47641),
            _bar(18.48, 18.88, 18.43, 18.79, 46556),
            _bar(18.75, 19.82, 18.75, 19.30, 97355),
            _bar(19.15, 20.25, 19.03, 20.05, 150672),
            _bar(20.90, 21.48, 20.35, 20.56, 228102),
        ],
        AS_OF,
    )
    reasons = risk_reasons(df, AS_OF)
    assert any("长上影" in r for r in reasons)
    assert any("放量阴线" in r for r in reasons)


def test_flags_chasing_high():
    """收盘偏离 MA10 超过 15% → 追高，不推。"""
    rows = [_bar(10, 10.1, 9.9, 10.0, 10000) for _ in range(10)]
    rows.append(_bar(11.8, 12.0, 11.7, 11.95, 12000))  # 偏离 MA10 约 +19%
    df = _frame(rows, AS_OF)
    assert any("追高" in r for r in risk_reasons(df, AS_OF))


def test_flags_missing_bar_on_as_of():
    """当日没有 K 线（停牌）→ 不推荐。"""
    df = _frame([_bar(10, 10.2, 9.9, 10.1, 10000)] * 5, AS_OF - timedelta(days=3))
    assert risk_reasons(df, AS_OF) == ["当日无成交"]


def test_empty_frame():
    assert risk_reasons(pd.DataFrame(), AS_OF) == ["无行情数据"]


@pytest.mark.parametrize(
    "vol_ratio,expect_flag",
    [(1.0, False), (1.4, False), (1.6, True)],
)
def test_upper_shadow_needs_volume(vol_ratio: float, expect_flag: bool):
    """长上影但不放量 → 不算硬伤（缩量上影常见于洗盘）。"""
    base = [_bar(10, 10.1, 9.9, 10.0, 10000) for _ in range(6)]
    # 上影占 60%，量按倍数给
    base.append(_bar(10.0, 10.6, 9.85, 10.05, 10000 * vol_ratio))
    df = _frame(base, AS_OF)
    flagged = any("长上影" in r for r in risk_reasons(df, AS_OF))
    assert flagged is expect_flag
