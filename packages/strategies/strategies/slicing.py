"""逐日全市场扫描的「位置切片」快路径（内存优化，阶段 10）。

## 为什么需要它

全市场逐日扫描的朴素写法是布尔掩码切片：

    sliced = {sym: candles[sym][candles[sym]["date"] <= day] for sym in symbols}

它有两个致命的内存问题（实测把 macOS jetsam 触发到反复 kill 扫描进程）：

1. **布尔掩码是复制，不是视图**：`df[mask]` 会把命中行的所有列重新分配一份。
   6000 只标的 × 300 根 × 7 列，每个交易日、每个策略、每个 worker 都复制一遍
   ≈ 每次 100MB+ 的分配/释放；240 个交易日 × 6 策略 = 上百万次 DataFrame 复制，
   分配 churn 让进程 RSS 一路抬高（CPython arena 不还给系统）。
2. **一次性物化整个宇宙**：字典推导会把 6000 份切片同时留在内存里，等策略扫完
   才释放，峰值 = 整个宇宙的一份完整副本。

## 快路径怎么做

- `date` 列（`datetime.date` 对象列）预先转成 int64 ordinal 数组，**每只标的只算一次**；
  用 `np.searchsorted(arr, day, "right")` O(log n) 得到「<= day 的行数」pos。
- 用 `df.iloc[:pos]` 做**位置切片**：前缀切片返回的是底层 ndarray 的视图，不复制数据。
- 用 `DaySliceView`（`Mapping`）**惰性**产出切片：策略遍历到哪只才切哪只，
  同一时刻只有一份切片活着，峰值内存从 O(宇宙) 降到 O(1)。

## 正确性前提（已在 packages/strategies 全部策略上核对）

- 所有策略的 `scan()/evaluate()` 只读传入的 frame（`df["close"].astype(float).tolist()`
  这类取列），没有任何就地写入，所以给视图是安全的。
- candles 的 date 列必须严格升序（通达信 .day 文件天然按日期升序）。
  `build_date_index` 会校验；不升序的标的会被标记为退化，交给调用方走慢路径。
- 前缀切片保留原 RangeIndex（0..pos-1），与布尔掩码切片的结果逐行、逐列、
  含 index 完全一致——见 tests/unit/test_slicing.py 的等价性单测。
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import date

import numpy as np
import pandas as pd

__all__ = ["DaySliceView", "build_date_index", "date_ordinals", "mask_slice"]


def date_ordinals(df: pd.DataFrame) -> np.ndarray:
    """把 `date` 列转成 int64 的 `date.toordinal()` 数组（用于 searchsorted）。"""
    col = df["date"]
    return np.fromiter(
        (d.toordinal() for d in col), dtype=np.int64, count=len(col)
    )


def build_date_index(
    candles: Mapping[str, pd.DataFrame],
) -> tuple[dict[str, np.ndarray], list[str]]:
    """为每只标的预计算 ordinal 数组。

    Returns:
        (date_index, degraded)：`date_index` 只含日期严格升序的标的；
        `degraded` 是日期非升序（searchsorted 不适用）的标的代码列表，
        调用方应对它们退回布尔掩码切片。
    """
    index: dict[str, np.ndarray] = {}
    degraded: list[str] = []
    for symbol, df in candles.items():
        if df is None or len(df) == 0:
            continue
        arr = date_ordinals(df)
        if arr.size > 1 and not bool(np.all(np.diff(arr) > 0)):
            degraded.append(symbol)
            continue
        index[symbol] = arr
    return index, degraded


def mask_slice(df: pd.DataFrame, day: date) -> pd.DataFrame:
    """慢路径（参考实现）：布尔掩码切片，仅供等价性校验与退化标的使用。"""
    return df[df["date"] <= day]


class DaySliceView(Mapping):
    """`{symbol: df.iloc[:pos]}` 的惰性只读视图（pos = date <= as_of 的行数）。

    只在 `__getitem__` 时做位置切片，因此策略遍历过程中同一时刻只有一份切片
    活着。`pos == 0`（该标的在 as_of 之前没有任何 K 线）的标的直接不出现在
    视图里——策略对空 frame 一律返回 None，所以信号结果与「给一个空 frame」等价。
    """

    __slots__ = ("_candles", "_pos")

    def __init__(
        self,
        candles: Mapping[str, pd.DataFrame],
        date_index: Mapping[str, np.ndarray],
        day: date,
        symbols: Mapping[str, object] | set[str] | None = None,
    ) -> None:
        key = day.toordinal()
        pos: dict[str, int] = {}
        iterable = candles if symbols is None else symbols
        for symbol in iterable:
            arr = date_index.get(symbol)
            if arr is None:
                continue
            p = int(np.searchsorted(arr, key, side="right"))
            if p:
                pos[symbol] = p
        self._candles = candles
        self._pos = pos

    def __getitem__(self, symbol: str) -> pd.DataFrame:
        return self._candles[symbol].iloc[: self._pos[symbol]]

    def __iter__(self) -> Iterator[str]:
        return iter(self._pos)

    def __len__(self) -> int:
        return len(self._pos)

    def __contains__(self, symbol: object) -> bool:
        return symbol in self._pos
