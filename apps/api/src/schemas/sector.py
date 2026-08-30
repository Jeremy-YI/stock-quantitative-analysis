"""板块资金流契约（top20 流入 / 流出 + 信号标签）。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from strategies.signal import Signal


class SectorFlow(BaseModel):
    """单个行业的资金流。金额单位：亿元。"""

    sector: str          # 行业名（同花顺口径）
    etf: str | None = None  # 对应 ETF（名称匹配，无匹配则 None）
    change_pct: float    # 行业涨跌幅 %
    inflow: float        # 流入资金（亿）
    outflow: float       # 流出资金（亿）
    net: float           # 净额（亿，正=流入，负=流出）
    companies: int       # 公司家数
    leader: str          # 领涨股名称
    leader_pct: float    # 领涨股涨幅 %
    signal: str | None = None  # 信号标签（"连续净流出可建仓" 等，暂无则 None）


class SectorFlowBody(BaseModel):
    """板块资金流响应体。"""

    days: str                       # 窗口：即时 / 3日 / 5日 / 10日 / 20日
    top_inflow: list[SectorFlow]    # 净流入前 20
    top_outflow: list[SectorFlow]   # 净流出前 20（net 为负）


class SectorInfo(BaseModel):
    """板块元信息（名称 + 成分股数）。"""

    name: str
    stock_count: int


class SectorListBody(BaseModel):
    """板块列表响应体。"""

    sectors: list[SectorInfo]


class RecommendationsBody(BaseModel):
    """板块个股推荐响应体（成分股 × 战法信号）。"""

    sector: str
    date: date
    signals: list[Signal]
