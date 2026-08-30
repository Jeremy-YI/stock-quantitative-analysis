"""板块资金流服务。

职责：读 data/sector_flow.json 快照（由 scripts/fetch_sector_flow.py 每天抓取），
转成契约对象返回。不直接调网络，保持 API 无 akshare 重依赖。

快照缺失时返回空（前端提示暂无数据），不抛异常。
"""

from __future__ import annotations

import json
from pathlib import Path

from schemas.sector import SectorFlow, SectorFlowBody

# 快照里的窗口 key（与 fetch 脚本一致）
DAYS = {"即时", "3日排行", "5日排行", "10日排行", "20日排行"}
_SNAPSHOT_PATH = Path(__file__).resolve().parents[4] / "data" / "sector_flow.json"


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

    def _load(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
