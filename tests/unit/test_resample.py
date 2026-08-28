"""多周期重采样单元测试：周线/月线聚合 + 停牌/长假/不完整周期边界。"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from market.resample import RULE_MONTHLY, RULE_WEEKLY, resample_ohlc


def _make_daily(records: list[tuple[str, float, float, float, float, int]]) -> pd.DataFrame:
    """records: (date, open, high, low, close, volume)，amount 由 close*volume 近似。"""
    return pd.DataFrame(
        {
            "date": [date.fromisoformat(d) for d, *_ in records],
            "open": [r[1] for r in records],
            "high": [r[2] for r in records],
            "low": [r[3] for r in records],
            "close": [r[4] for r in records],
            "volume": [r[5] for r in records],
            "amount": [r[4] * r[5] for r in records],
        }
    )


def test_weekly_aggregates_natural_week():
    """完整自然周（周一~周五）→ 一根周线：open 首 / high 最大 / low 最小 / close 末 / volume 求和。"""
    df = _make_daily(
        [
            ("2026-03-02", 10.0, 11.0, 9.5, 10.5, 100),  # 周一
            ("2026-03-03", 10.5, 11.5, 10.0, 11.0, 120),
            ("2026-03-04", 11.0, 12.0, 10.8, 11.8, 130),
            ("2026-03-05", 11.8, 12.2, 11.0, 11.5, 110),
            ("2026-03-06", 11.5, 11.9, 11.0, 11.2, 90),  # 周五
        ]
    )
    out = resample_ohlc(df, RULE_WEEKLY)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["open"] == 10.0  # 首日开盘
    assert row["high"] == 12.2  # 全周最高
    assert row["low"] == 9.5  # 全周最低
    assert row["close"] == 11.2  # 末日收盘
    assert row["volume"] == 100 + 120 + 130 + 110 + 90


def test_weekly_splits_two_weeks():
    """跨周数据切成两根周线，索引为各周周五。"""
    df = _make_daily(
        [
            ("2026-03-05", 10.0, 10.5, 9.8, 10.2, 100),  # 周四（第 1 周）
            ("2026-03-06", 10.2, 10.6, 10.0, 10.4, 110),  # 周五（第 1 周）
            ("2026-03-09", 10.4, 11.0, 10.2, 10.8, 120),  # 周一（第 2 周）
            ("2026-03-10", 10.8, 11.2, 10.6, 11.0, 130),  # 周二（第 2 周）
        ]
    )
    out = resample_ohlc(df, RULE_WEEKLY)
    assert len(out) == 2
    # 索引分别是两个周五
    assert out.index[0] == pd.Timestamp("2026-03-06")
    assert out.index[1] == pd.Timestamp("2026-03-13")
    assert out.iloc[0]["close"] == 10.4
    assert out.iloc[1]["close"] == 11.0


def test_weekly_skips_empty_holiday_week():
    """中间整周停牌 → 该周不生成行。"""
    df = _make_daily(
        [
            ("2026-03-06", 10.0, 10.5, 9.8, 10.2, 100),  # 第 1 周
            ("2026-03-16", 10.2, 11.0, 10.0, 10.8, 120),  # 第 3 周（第 2 周整周空）
        ]
    )
    out = resample_ohlc(df, RULE_WEEKLY)
    assert len(out) == 2  # 只有两根，中间空周被 dropna 掉


def test_weekly_incomplete_last_week():
    """最后一周不满 5 天 → 仍生成，open/close 取该周实际首/末日。"""
    df = _make_daily(
        [
            ("2026-03-02", 10.0, 11.0, 9.5, 10.5, 100),
            ("2026-03-03", 10.5, 11.5, 10.0, 11.0, 120),
            ("2026-03-04", 11.0, 12.0, 10.8, 11.8, 130),  # 周三后停牌
        ]
    )
    out = resample_ohlc(df, RULE_WEEKLY)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["open"] == 10.0
    assert row["close"] == 11.8  # 最后交易日是周三
    assert row["volume"] == 350


def test_monthly_aggregates_natural_month():
    """跨两个月的日线 → 两根月线。"""
    df = _make_daily(
        [
            ("2026-01-29", 10.0, 11.0, 9.5, 10.5, 100),
            ("2026-01-30", 10.5, 11.2, 10.0, 11.0, 120),  # 1 月最后交易日
            ("2026-02-02", 11.0, 12.0, 10.8, 11.8, 130),
            ("2026-02-27", 11.8, 12.5, 11.0, 12.0, 140),  # 2 月
        ]
    )
    out = resample_ohlc(df, RULE_MONTHLY)
    assert len(out) == 2
    assert out.index[0] == pd.Timestamp("2026-01-31")
    assert out.index[1] == pd.Timestamp("2026-02-28")
    assert out.iloc[0]["close"] == 11.0
    assert out.iloc[1]["close"] == 12.0
    assert out.iloc[1]["volume"] == 130 + 140


def test_amount_summed_when_present():
    df = _make_daily(
        [
            ("2026-03-02", 10.0, 11.0, 9.5, 10.5, 100),
            ("2026-03-03", 10.5, 11.5, 10.0, 11.0, 120),
        ]
    )
    out = resample_ohlc(df, RULE_WEEKLY)
    assert out.iloc[0]["amount"] == 10.5 * 100 + 11.0 * 120


def test_empty_input_returns_empty():
    empty = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    out = resample_ohlc(empty, RULE_WEEKLY)
    assert out.empty


def test_single_row():
    df = _make_daily([("2026-03-02", 10.0, 10.5, 9.5, 10.2, 100)])
    out = resample_ohlc(df, RULE_WEEKLY)
    assert len(out) == 1
    assert out.iloc[0]["open"] == 10.0
    assert out.iloc[0]["close"] == 10.2
