"""市场资讯服务（最新消息 / 事件日历）。

职责：读 data/news.json 和 data/events.json 快照，转成契约对象。
数据源目前是种子快照；后续可接定时采集（财经快讯 cron / 事件日历数据源）。
"""

from __future__ import annotations

import json
from pathlib import Path

from schemas.market import EventItem, EventsBody, NewsBody, NewsItem

_REPO_ROOT = Path(__file__).resolve().parents[4]
_NEWS_PATH = _REPO_ROOT / "data" / "news.json"
_EVENTS_PATH = _REPO_ROOT / "data" / "events.json"


class MarketService:
    """市场资讯查询服务（无状态）。"""

    def get_news(self) -> NewsBody:
        raw = self._load(_NEWS_PATH)
        return NewsBody(
            date=raw.get("date", ""),
            source=raw.get("source", ""),
            items=[NewsItem(**x) for x in raw.get("items", [])],
        )

    def get_events(self) -> EventsBody:
        raw = self._load(_EVENTS_PATH)
        return EventsBody(
            note=raw.get("note", ""),
            events=[EventItem(**x) for x in raw.get("events", [])],
        )

    @staticmethod
    def _load(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
