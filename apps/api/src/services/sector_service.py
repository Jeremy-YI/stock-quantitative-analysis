"""板块资金流服务。

职责：读 data/sector_flow.json 快照（由 scripts/fetch_sector_flow.py 每天抓取），
转成契约对象返回。不直接调网络，保持 API 无 akshare 重依赖。

快照缺失时返回空（前端提示暂无数据），不抛异常。
"""

from __future__ import annotations

import json
from pathlib import Path

from schemas.sector import SectorFlow, SectorFlowBody, SectorInfo

# 快照里的窗口 key（与 fetch 脚本一致）
DAYS = {"即时", "3日排行", "5日排行", "10日排行", "20日排行"}
_SNAPSHOT_PATH = Path(__file__).resolve().parents[4] / "data" / "sector_flow.json"
_STOCKS_PATH = Path(__file__).resolve().parents[4] / "data" / "sector_stocks.json"


class SectorService:
    """板块资金流查询服务（无状态）。"""

    def __init__(self, snapshot_path: str | None = None) -> None:
        self._path = Path(snapshot_path) if snapshot_path else _SNAPSHOT_PATH

    def sector_flow(self, days: str = "即时") -> SectorFlowBody:
        if days not in DAYS:
            days = "即时"
        raw = self._load()
        data = raw.get(days, {"top_inflow": [], "top_outflow": []})
        return SectorFlowBody(
            days=days,
            top_inflow=[SectorFlow(**x) for x in data.get("top_inflow", [])],
            top_outflow=[SectorFlow(**x) for x in data.get("top_outflow", [])],
        )

    def list_sectors(self) -> list[SectorInfo]:
        """返回板块列表（名称 + 成分股数）。"""
        stocks = self._load_stocks()
        return [SectorInfo(name=k, stock_count=len(v)) for k, v in sorted(stocks.items())]

    def get_constituents(self, name: str) -> list[str]:
        """返回某板块的成分股代码列表（无此板块返回空）。"""
        stocks = self._load_stocks()
        return list(stocks.get(name, []))

    def _load(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _load_stocks(self) -> dict[str, list[str]]:
        """读板块成分股（data/sector_stocks.json，格式 {板块名: {code, stocks[]}}）。"""
        try:
            raw = json.loads(_STOCKS_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        out: dict[str, list[str]] = {}
        for name, val in raw.items():
            if isinstance(val, dict) and "stocks" in val:
                out[name] = list(val["stocks"])
        return out
