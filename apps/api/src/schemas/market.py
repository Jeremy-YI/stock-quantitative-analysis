"""市场资讯契约（最新消息 / 事件日历）。"""

from __future__ import annotations

from pydantic import BaseModel


class RelatedSymbol(BaseModel):
    """受消息影响的相关标的。"""

    symbol: str
    name: str
    reason: str


class NewsItem(BaseModel):
    """一条宏观消息。"""

    id: str = ""
    title: str
    impact: str       # 影响评级：改变定价 / 显著影响 / 结构性关注
    level: str        # P0 / P1 / P2
    outlook: str      # 未来导向
    sources: int      # 来源数
    detail: str = ""              # 详细解读（点开后看的内容）
    topics: list[str] = []        # 主题标签
    related_symbols: list[RelatedSymbol] = []  # 相关标的


class NewsBody(BaseModel):
    date: str
    source: str
    items: list[NewsItem]


class NewsDetailBody(BaseModel):
    """单条消息的详情：全文 + 相关标的 + 相关消息。"""

    item: NewsItem
    date: str = ""
    source: str = ""
    related_news: list[NewsItem] = []  # 同主题的其他消息


class EventHistory(BaseModel):
    """事件的历史发生记录与当时市场反应。"""

    date: str
    note: str


class EventItem(BaseModel):
    """一条关键事件（会议/数据/财报）。"""

    id: str = ""
    date: str
    name: str
    type: str         # 央行会议 / 数据 / 财报
    importance: str   # 高 / 中 / 低
    description: str = ""            # 事件是什么、为什么重要
    history: list[EventHistory] = []  # 历史发生记录与市场反应


class EventsBody(BaseModel):
    note: str
    events: list[EventItem]


class EventDetailBody(BaseModel):
    """单个事件的详情：说明 + 历史数据。"""

    event: EventItem
    note: str = ""
