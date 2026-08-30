"""板块资金流 + 板块个股推荐路由。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from schemas.common import ApiResponse
from schemas.sector import RecommendationsBody, SectorFlowBody, SectorListBody
from services.sector_service import SectorService
from services.strategy_service import StrategyService

router = APIRouter(tags=["sectors"])


def get_sector_service(request: Request) -> SectorService:
    """从应用状态取 sector service（测试时可注入 fake）。"""
    return request.app.state.sector_service


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


@router.get("/sectors/{name}/recommendations", response_model=ApiResponse[RecommendationsBody])
def sector_recommendations(
    name: str,
    date_: date = Query(..., alias="date", description="扫描日（YYYY-MM-DD）"),
    sector_service: SectorService = Depends(get_sector_service),
    strategy_service: StrategyService = Depends(get_strategy_service),
) -> ApiResponse[RecommendationsBody]:
    """板块成分股 × 战法信号：对板块成分股跑全部策略，返回触发的信号。"""
    symbols = sector_service.get_constituents(name)
    signals = []
    for info in strategy_service.list_strategies():
        signals.extend(strategy_service.scan_subset(info.name, date_, symbols))
    # 按分数降序，方便前端直接展示最优先的
    signals.sort(key=lambda s: s.score, reverse=True)
    return ApiResponse(
        message="ok",
        body=RecommendationsBody(sector=name, date=date_, signals=signals),
    )
