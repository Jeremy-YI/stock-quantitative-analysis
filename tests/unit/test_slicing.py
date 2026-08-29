"""位置切片快路径（strategies.slicing）单测：与布尔掩码切片必须逐条等价。

覆盖点（阶段 10 内存修复的正确性护栏）：
1. `DaySliceView[symbol]` 与 `df[df["date"] <= day]` 的结果 frame 完全一致
   （行数、列、index、数值）。
2. 位置切片是视图（不复制底层数据）。
3. 真实策略 `scan()` 在两种切片下产出的信号集合完全一致。
4. 非升序日期会被 `build_date_index` 标记为退化（不会静默给错结果）。
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from strategies import macd_volume_washout, pin30
from strategies.slicing import DaySliceView, build_date_index, date_ordinals, mask_slice


def _frame(n: int, end: date = date(2024, 6, 28), seed: int = 0) -> pd.DataFrame:
    """生成 n 根工作日日线（伪随机但确定），date 列为 datetime.date 对象。"""
    rng = np.random.default_rng(seed)
    days: list[date] = []
    day = end
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    days = list(reversed(days))
    close = 10.0 + np.cumsum(rng.normal(0, 0.25, n))
    close = np.maximum(close, 1.0)
    return pd.DataFrame(
        {
            "date": days,
            "open": close * 0.99,
            "high": close * 1.02,
            "low": close * 0.97,
            "close": close,
            "volume": (rng.integers(3000, 30000, n)).astype(float),
            "amount": close * rng.integers(3_000_000, 30_000_000, n),
        }
    )


def test_date_ordinals_matches_python_toordinal() -> None:
    df = _frame(20)
    arr = date_ordinals(df)
    assert arr.dtype == np.int64
    assert arr.tolist() == [d.toordinal() for d in df["date"]]


def test_slice_view_equals_boolean_mask() -> None:
    """核心回归护栏：位置切片 == 布尔掩码切片（逐行逐列逐 index）。"""
    candles = {"600000": _frame(120, seed=1), "000001": _frame(80, seed=2)}
    index, degraded = build_date_index(candles)
    assert degraded == []

    all_days = sorted({d for df in candles.values() for d in df["date"]})
    # 覆盖：区间内每一天 + 区间外（早于全部 / 晚于全部）+ 非交易日（周末）
    probes = all_days + [date(2000, 1, 1), date(2030, 1, 1), date(2024, 6, 29)]
    for day in probes:
        view = DaySliceView(candles, index, day)
        for symbol, df in candles.items():
            expected = mask_slice(df, day)
            if expected.empty:
                assert symbol not in view
                continue
            got = view[symbol]
            pd.testing.assert_frame_equal(got, expected)


def test_slice_view_is_a_view_not_a_copy() -> None:
    """位置切片必须共享底层内存（这才是省内存的关键）。"""
    candles = {"600000": _frame(60, seed=3)}
    index, _ = build_date_index(candles)
    day = candles["600000"]["date"].iloc[40]
    view = DaySliceView(candles, index, day)
    sliced = view["600000"]
    assert len(sliced) == 41
    assert np.shares_memory(
        sliced["close"].to_numpy(), candles["600000"]["close"].to_numpy()
    )


def test_slice_view_len_iter_and_missing_symbol() -> None:
    candles = {"600000": _frame(30, seed=4), "600001": _frame(30, seed=5)}
    index, _ = build_date_index(candles)
    day = candles["600000"]["date"].iloc[10]
    view = DaySliceView(candles, index, day)
    assert len(view) == 2
    assert sorted(view) == ["600000", "600001"]
    assert "999999" not in view
    with pytest.raises(KeyError):
        view["999999"]

    # symbols 参数限制宇宙
    subset = DaySliceView(candles, index, day, symbols={"600001"})
    assert sorted(subset) == ["600001"]


@pytest.mark.parametrize("module", [macd_volume_washout, pin30])
def test_strategy_scan_identical_under_both_slicings(module) -> None:
    """真实策略在两种切片下的信号集合必须一致（含 score / metrics）。"""
    candles = {
        "600%03d" % i: _frame(200, seed=10 + i) for i in range(12)
    }
    index, _ = build_date_index(candles)
    days = sorted({d for df in candles.values() for d in df["date"]})[-15:]

    for day in days:
        slow = {
            sym: mask_slice(df, day) for sym, df in candles.items()
        }
        slow_sigs = module.scan(slow, day)
        fast_sigs = module.scan(DaySliceView(candles, index, day), day)

        def key(s):
            return (s.strategy, s.symbol, s.triggered_at, s.score, tuple(sorted(s.metrics.items())))

        assert [key(s) for s in slow_sigs] == [key(s) for s in fast_sigs]

    # 源数据没被切片视图污染（策略只读的前提校验）
    for sym, df in candles.items():
        assert len(df) == 200
        assert not df["close"].isna().any()


def test_non_monotonic_dates_are_flagged_degraded() -> None:
    df = _frame(10, seed=6)
    df.loc[3, "date"] = df["date"].iloc[8]  # 打乱升序
    index, degraded = build_date_index({"600000": df})
    assert degraded == ["600000"]
    assert index == {}
