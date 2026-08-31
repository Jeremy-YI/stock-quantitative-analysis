"""板块资金流 + 板块个股推荐路由。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from schemas.common import ApiResponse
from schemas.sector import (
    EtfFlowBody,
    RecommendationsBody,
    RecommendedStock,
    SectorFlowBody,
    SectorListBody,
)
from services.sector_service import SectorService
from services.stock_meta_service import StockMetaService
from services.strategy_service import StrategyService

router = APIRouter(tags=["sectors"])


def get_sector_service(request: Request) -> SectorService:
    """从应用状态取 sector service（测试时可注入 fake）。"""
    return request.app.state.sector_service


def get_stock_meta_service(request: Request) -> StockMetaService:
    """股票名称 / ST 服务。"""
    return request.app.state.stock_meta_service


def get_strategy_service(request: Request) -> StrategyService:
    """取 strategy service（板块推荐要用它扫成分股信号）。"""
    return request.app.state.strategy_service


@router.get("/sectors", response_model=ApiResponse[SectorListBody])
def list_sectors(
    service: SectorService = Depends(get_sector_service),
) -> ApiResponse[SectorListBody]:
    """板块列表（名称 + 成分股数）。"""
    return ApiResponse(message="ok", body=SectorListBody(sectors=service.list_sectors()))


@router.get("/sectors/flow", response_model=ApiResponse[SectorFlowBody])
def sector_flow(
    days: str = Query("即时", description="窗口：即时/3日排行/5日排行/10日排行/20日排行"),
    service: SectorService = Depends(get_sector_service),
) -> ApiResponse[SectorFlowBody]:
    """板块资金流：top20 净流入 + top20 净流出。"""
    return ApiResponse(message="ok", body=service.sector_flow(days))


@router.get("/sectors/etf-flow", response_model=ApiResponse[EtfFlowBody])
def etf_flow(
    top: int = Query(20, ge=1, le=50, description="每侧取前多少名"),
    service: SectorService = Depends(get_sector_service),
) -> ApiResponse[EtfFlowBody]:
    """ETF 资金流：净流入 / 净流出 TOP N（已过滤货币、债券、迷你盘）。

    路径必须写在 /sectors/{name} 之前，否则会被动态段吃掉。
    """
    return ApiResponse(message="ok", body=service.etf_flow(top))


@router.get("/sectors/{name}/recommendations", response_model=ApiResponse[RecommendationsBody])
def sector_recommendations(
    name: str,
    date_: date = Query(..., alias="date", description="扫描日（YYYY-MM-DD）"),
    include_st: bool = Query(
        False, description="是否包含 ST/退市整理期股票（默认不包含，不推荐给客户）"
    ),
    sector_service: SectorService = Depends(get_sector_service),
    strategy_service: StrategyService = Depends(get_strategy_service),
    meta: StockMetaService = Depends(get_stock_meta_service),
) -> ApiResponse[RecommendationsBody]:
    """板块成分股 × 战法信号。

    两个产品约定：
      1. **默认剔除 ST / 退市整理期**（风险警示股不推荐给客户），扫描前就过滤，
         既安全也省算力；真要看可以显式传 include_st=true
      2. 返回按股票聚合的 stocks（带证券简称），前端不用自己分组
    """
    symbols = sector_service.get_constituents(name)
    total = len(symbols)
    if not include_st:
        symbols = meta.filter_tradable(symbols)
    excluded_st = total - len(symbols)

    signals = []
    for info in strategy_service.list_strategies():
        signals.extend(strategy_service.scan_subset(info.name, date_, symbols))
    # 按分数降序，方便前端直接展示最优先的
    signals.sort(key=lambda s: s.score, reverse=True)

    return ApiResponse(
        message="ok",
        body=RecommendationsBody(
            sector=name,
            date=date_,
            signals=signals,
            stocks=_group_by_stock(signals, meta),
            excluded_st=excluded_st,
            names_available=meta.available(),
        ),
    )


@router.get("/stocks/{symbol}/signals", response_model=ApiResponse[RecommendationsBody])
def stock_signals(
    symbol: str,
    date_: date = Query(..., alias="date", description="扫描日（YYYY-MM-DD）"),
    strategy_service: StrategyService = Depends(get_strategy_service),
    meta: StockMetaService = Depends(get_stock_meta_service),
) -> ApiResponse[RecommendationsBody]:
    """单只个股的全部战法信号（个股详情页：买入信号列表 + K 线标记）。"""
    signals = []
    for info in strategy_service.list_strategies():
        signals.extend(strategy_service.scan_subset(info.name, date_, [symbol]))
    signals.sort(key=lambda s: s.score, reverse=True)

    return ApiResponse(
        message="ok",
        body=RecommendationsBody(
            sector="",
            date=date_,
            signals=signals,
            stocks=_group_by_stock(signals, meta),
            excluded_st=0,
            names_available=meta.available(),
        ),
    )


def _group_by_stock(signals: list, meta: StockMetaService) -> list[RecommendedStock]:
    """信号列表 → 按股票聚合（带名称，按最高分降序）。"""
    grouped: dict[str, list] = {}
    for sig in signals:
        grouped.setdefault(sig.symbol, []).append(sig)
    stocks = [
        RecommendedStock(
            symbol=symbol,
            name=meta.name(symbol),
            score=max(s.score for s in group),
            signals=group,
        )
        for symbol, group in grouped.items()
    ]
    stocks.sort(key=lambda s: s.score, reverse=True)
    return stocks
