"""市场资讯契约（最新消息 / 事件日历）。"""

from __future__ import annotations

from pydantic import BaseModel


class NewsItem(BaseModel):
    """一条宏观消息。"""

    title: str
    impact: str       # 影响评级：改变定价 / 显著影响 / 结构性关注
    level: str        # P0 / P1 / P2
    outlook: str      # 未来导向
    sources: int      # 来源数


class NewsBody(BaseModel):
    date: str
    source: str
    items: list[NewsItem]


class EventItem(BaseModel):
    """一条关键事件（会议/数据/财报）。"""

    date: str
    name: str
    type: str         # 央行会议 / 数据 / 财报
    importance: str   # 高 / 中 / 低


class EventsBody(BaseModel):
    note: str
    events: list[EventItem]
