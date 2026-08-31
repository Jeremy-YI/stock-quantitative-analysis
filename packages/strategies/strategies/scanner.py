"""全市场扫描器：遍历 hsjday 全量 .day 文件，过滤后组装成 candles dict。

职责边界：
    - 只负责「读文件 → 过滤 → 组装 dict」，不做任何策略计算。
    - 过滤规则见 ``strategies.filters``，ST 名称通过 ``name_map`` 可选注入。
    - 策略层通过统一接口 ``scan(candles, as_of, config)`` 消费 candles。

性能说明：每只标的独立一个 .day 文件，逐文件读取是唯一物理成本；
为控制成本只读文件尾部 ``lookback`` 根 K 线（策略所需的回看窗口上限），
指标计算在策略层用 packages/indicators（与旧脚本同源），全量实测耗时见
docs/策略迁移说明.md。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Collection, Protocol

import pandas as pd

from datasource.tdx import COLUMNS, RECORD_SIZE, parse_records, resolve_price_divisor, symbol_from_path
from strategies.filters import FilterConfig, classify_symbol, kind_excluded, should_include

# 扫描遍历的市场（顺序固定，保证输出可复现）
_MARKETS = ("sh", "sz", "bj")

# 默认回看 K 线根数：月线共振需 30 个月 ≈ 660 日，留余量取 800
DEFAULT_LOOKBACK = 800


class Scanner(Protocol):
    """扫描器协议：service 只依赖此接口，测试可注入 Fake。"""

    def load_candles(
        self, as_of: date, filter_config: FilterConfig | None = None
    ) -> dict[str, pd.DataFrame]:
        """返回 {6 位代码: 日线 DataFrame}（已过滤）。"""
        ...


class MarketScanner:
    """从本地 hsjday 目录读取全量日线并过滤。"""

    def __init__(
        self,
        hsjday_root: Path,
        filter_config: FilterConfig | None = None,
        name_map: dict[str, str] | None = None,
        lookback: int = DEFAULT_LOOKBACK,
    ) -> None:
        self._root = Path(hsjday_root)
        self._filter = filter_config or FilterConfig()
        self._name_map = name_map or {}
        self._lookback = lookback

    def load_candles(
        self,
        as_of: date,
        filter_config: FilterConfig | None = None,
        symbols: Collection[str] | None = None,
    ) -> dict[str, pd.DataFrame]:
        """遍历全量 .day 文件，返回通过过滤的 candles。

        filter_config 为 None 时用构造时传入的默认过滤；否则临时覆盖。
        symbols 非空时只加载指定代码（分片扫描用，阶段 5 调度器断点续跑）。
        """
        cfg = filter_config or self._filter
        symbol_set = set(symbols) if symbols is not None else None
        candles: dict[str, pd.DataFrame] = {}

        for market in _MARKETS:
            lday_dir = self._root / market / "lday"
            if not lday_dir.is_dir():
                continue
            for fn in sorted(lday_dir.iterdir()):
                if not fn.name.endswith(".day"):
                    continue
                # 文件名形如 sh600519.day / sz000001.day
                code = fn.name[2:8]
                if len(code) != 6:
                    continue

                # 分片：只加载指定代码（跳过其余，省去读文件成本）
                if symbol_set is not None and code not in symbol_set:
                    continue

                # 先按代码前缀短路剔除 ETF/指数/可转债/基金，避免读文件
                if kind_excluded(classify_symbol(market, code), cfg):
                    continue

                # 上市天数用文件总记录数（= 文件大小/32），与尾读窗口解耦
                total_bars = fn.stat().st_size // RECORD_SIZE

                df = _read_day_tail(fn, self._lookback)
                if df.empty:
                    continue

                last_trade_date = df["date"].iloc[-1]
                amount = float(df["amount"].iloc[-1])
                name = self._name_map.get(code)

                if not should_include(
                    market=market,
                    code=code,
                    n_bars=total_bars,
                    last_trade_date=last_trade_date,
                    as_of=as_of,
                    amount=amount,
                    name=name,
                    cfg=cfg,
                ):
                    continue

                candles[code] = df

        return candles

    def list_symbols(self, filter_config: FilterConfig | None = None) -> list[str]:
        """枚举候选标的代码（只按代码前缀种类过滤，不读文件）。

        供分片扫描在真正读文件前切分宇宙；返回升序的 6 位代码列表。
        """
        cfg = filter_config or self._filter
        codes: set[str] = set()
        for market in _MARKETS:
            lday_dir = self._root / market / "lday"
            if not lday_dir.is_dir():
                continue
            for fn in sorted(lday_dir.iterdir()):
                if not fn.name.endswith(".day"):
                    continue
                code = fn.name[2:8]
                if len(code) != 6:
                    continue
                if kind_excluded(classify_symbol(market, code), cfg):
                    continue
                codes.add(code)
        return sorted(codes)


def _read_day_tail(path: Path, n_records: int) -> pd.DataFrame:
    """只读 .day 文件尾部 ``n_records`` 根 K 线（不足则全读）。

    通达信 .day 为定长 32 字节记录，尾部读可以跳过全量 struct 解包，
    大幅降低全市场扫描成本（策略只需有限回看窗口）。
    """
    size = path.stat().st_size
    if size <= n_records * RECORD_SIZE:
        data = path.read_bytes()
    else:
        with path.open("rb") as f:
            f.seek(size - n_records * RECORD_SIZE)
            data = f.read()

    records = parse_records(data, resolve_price_divisor(symbol_from_path(path)))
    if not records:
        return pd.DataFrame(columns=COLUMNS)
    return pd.DataFrame.from_records(records, columns=COLUMNS)
