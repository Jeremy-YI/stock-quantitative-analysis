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


class EtfFlow(BaseModel):
    """单只场内 ETF 的资金流。金额单位：亿元。

    两个口径分开给，前端可切换：
      net       主力净流入（东财大单口径）——当天盘口强弱
      share_net 份额变化 × 最新价——申赎的真金白银，需隔日对比，首日为 None
    """

    code: str                      # ETF 代码
    name: str                      # ETF 名称
    price: float                   # 最新价
    change_pct: float              # 涨跌幅 %
    net: float | None = None       # 主力净流入（亿）；非交易日/历史不可回溯时为 None
    net_ratio: float | None = None  # 主力净流入占成交额比 %
    turnover: float                # 成交额（亿）
    turnover_rate: float           # 换手率 %
    mcap: float                    # 流通市值（亿）
    share_net: float | None = None  # 份额变化估算净申购（亿），无历史时 None


class EtfLeader(EtfFlow):
    """主题龙头 ETF：同一主题里资金最集中（流通市值最大）的那一只。

    参考站点把同一指数下所有 ETF 全列出来，对做决策没必要；
    这里每个主题只给一只代表标的。
    """

    category: str   # 大类：宽基 / 科技成长 / 医药消费 / 金融地产 / 周期资源 / 红利防御 / 跨境
    theme: str      # 主题：半导体/芯片、红利低波…
    peers: int = 1  # 该主题下共有多少只 ETF（当前展示的是其中最大的）


class EtfFlowBody(BaseModel):
    """ETF 资金流响应体（主题龙头 + 净流入/净流出 TOP N）。"""

    date: str                    # 数据日期（YYYY-MM-DD，快照缺失为空串）
    total: int                   # 参与排行的 ETF 数（已过滤货币/债券/迷你盘）
    has_share_flow: bool         # 份额口径是否可用（需要前一日快照）
    flow_available: bool = True   # 大单口径是否可用（非交易日快照拿不到）
    leaders: list[EtfLeader] = []  # 主题龙头（按宽基→成长→…的固定顺序）
    top_inflow: list[EtfFlow]    # 净流入 TOP
    top_outflow: list[EtfFlow]   # 净流出 TOP


class SectorInfo(BaseModel):
    """板块元信息（名称 + 成分股数）。"""

    name: str
    stock_count: int


class SectorListBody(BaseModel):
    """板块列表响应体。"""

    sectors: list[SectorInfo]


class RecommendedStock(BaseModel):
    """一只被推荐的个股（按最高分排序，前端直接渲染）。"""

    symbol: str                 # 6 位代码
    name: str                   # 证券简称（快照缺失时为空串）
    score: float                # 该股触发信号里的最高分
    signals: list[Signal]       # 触发的全部信号


class RecommendationsBody(BaseModel):
    """板块个股推荐响应体（成分股 × 战法信号）。

    stocks 是按股票聚合后的结果（含名称），signals 保留扁平列表向后兼容。
    """

    sector: str
    date: date
    signals: list[Signal]
    stocks: list[RecommendedStock] = []
    excluded_st: int = 0          # 因风险警示（ST/退市）被剔除的股票数
    names_available: bool = True  # 名称快照是否可用（false 时未做 ST 过滤）
