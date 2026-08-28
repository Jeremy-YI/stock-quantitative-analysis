"""日线数据仓储。

阶段 1：基于本地通达信 hsjday 文件（只读）的实现 TdxDailyBarRepository。
阶段 2：MySqlDailyBarRepository 从 daily_bars 表读取（见 migrations/）。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Protocol

import pandas as pd

from datasource.tdx import parse_day_file, resolve_symbol_path
from errors import InsufficientDataError, SymbolNotFoundError


class DailyBarRepository(Protocol):
    """日线仓储接口。service 层只依赖此协议，不感知底层是文件还是 MySQL。"""

    def get_daily_bars(
        self, symbol: str, start: date | None = None, end: date | None = None
    ) -> pd.DataFrame:
        """按代码 + 可选日期区间返回日线 DataFrame（columns 同 datasource.COLUMNS）。"""
        ...


class TdxDailyBarRepository:
    """从本地 hsjday .day 文件读取日线。"""

    def __init__(self, hsjday_root: Path) -> None:
        self._root = hsjday_root

    def get_daily_bars(
        self, symbol: str, start: date | None = None, end: date | None = None
    ) -> pd.DataFrame:
        path = resolve_symbol_path(self._root, symbol)
        if not path.exists():
            raise SymbolNotFoundError(f"标的 {symbol} 不存在（{path}）")

        df = parse_day_file(path)
        if df.empty:
            raise InsufficientDataError(f"标的 {symbol} 无日线数据")

        # 按日期区间过滤（闭区间）
        if start is not None:
            df = df[df["date"] >= start]
        if end is not None:
            df = df[df["date"] <= end]

        if df.empty:
            raise InsufficientDataError(
                f"标的 {symbol} 在 {start} ~ {end} 区间内无日线数据"
            )
        return df.reset_index(drop=True)
