"""股票元信息服务：代码 → 名称 + 是否风险警示（ST/退市）。

职责边界：
  - 只读 data/stock_names.json 快照（scripts/fetch_stock_names.py 落盘）
  - 给推荐/详情接口补名称，并**把 ST、退市整理期的票挡在推荐之外**
    （风险警示股票不推荐给客户，这是产品红线，不是可选项）

快照缺失时不抛异常：名称回退为空、is_st 一律 False（宁可少过滤也别让接口 500），
但会在 meta.available 里如实告知前端。
"""

from __future__ import annotations

import json
from pathlib import Path

_NAMES_PATH = Path(__file__).resolve().parents[4] / "data" / "stock_names.json"
# 场内基金名称表（scripts/fetch_etf_flow.py 落盘，code → name）
_ETF_NAMES_PATH = Path(__file__).resolve().parents[4] / "data" / "etf_universe.json"

# 场内基金代码前缀（沪 50/51/52/56/58，深 15/16/18）
_FUND_PREFIXES = ("50", "51", "52", "56", "58", "15", "16", "18")


class StockMetaService:
    """股票名称 / ST 标记查询（无状态，懒加载一次）。"""

    def __init__(self, names_path: str | None = None, etf_names_path: str | None = None) -> None:
        self._path = Path(names_path) if names_path else _NAMES_PATH
        self._etf_path = Path(etf_names_path) if etf_names_path else _ETF_NAMES_PATH
        self._cache: dict[str, dict] | None = None
        self._etf_cache: dict[str, str] | None = None
        self._as_of: str = ""

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def name(self, symbol: str) -> str:
        """名称；A股查 stock_names，ETF/LOF 回落到 etf_universe；查不到返回空串。"""
        found = self._stocks().get(symbol, {}).get("name", "")
        if found:
            return found
        return self._etf_names().get(symbol, "")

    @staticmethod
    def is_fund(symbol: str) -> bool:
        """是否场内基金（ETF/LOF）。基金没有 ST 概念，也不参与个股推荐过滤。"""
        return symbol.startswith(_FUND_PREFIXES)

    def is_st(self, symbol: str) -> bool:
        """是否风险警示（ST/*ST/退市整理期）。查不到按 False 处理。"""
        return bool(self._stocks().get(symbol, {}).get("st", False))

    def available(self) -> bool:
        """名称快照是否可用（前端可据此提示「未过滤 ST」）。"""
        return bool(self._stocks())

    def as_of(self) -> str:
        self._stocks()
        return self._as_of

    def filter_tradable(self, symbols: list[str]) -> list[str]:
        """剔除风险警示股票，保持原顺序。"""
        return [s for s in symbols if not self.is_st(s)]

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _etf_names(self) -> dict[str, str]:
        if self._etf_cache is None:
            try:
                raw = json.loads(self._etf_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                raw = {}
            self._etf_cache = {
                str(k): str(v) for k, v in raw.items() if isinstance(v, str)
            } if isinstance(raw, dict) else {}
        return self._etf_cache

    def _stocks(self) -> dict[str, dict]:
        if self._cache is None:
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                raw = {}
            self._cache = raw.get("stocks", {}) if isinstance(raw, dict) else {}
            self._as_of = str(raw.get("as_of", "")) if isinstance(raw, dict) else ""
        return self._cache
