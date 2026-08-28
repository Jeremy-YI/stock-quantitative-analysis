"""策略路由。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from schemas.common import ApiResponse
from schemas.strategy import ScanBody, SignalsBody, StrategyListBody
from services.strategy_service import StrategyService

router = APIRouter(tags=["strategies"])


def get_strategy_service(request: Request) -> StrategyService:
    """从应用状态取 service 实例（测试时可注入 fake scanner/repository）。"""
    return request.app.state.strategy_service


@router.get("/strategies", response_model=ApiResponse[StrategyListBody])
def list_strategies(
    service: StrategyService = Depends(get_strategy_service),
) -> ApiResponse[StrategyListBody]:
    """列出可用策略及其配置说明。"""
    return ApiResponse(
        message="ok",
        body=StrategyListBody(strategies=service.list_strategies()),
    )


@router.get("/strategies/{name}/scan", response_model=ApiResponse[ScanBody])
def scan_strategy(
    name: str,
    date_: date = Query(..., alias="date", description="扫描日（YYYY-MM-DD）"),
    service: StrategyService = Depends(get_strategy_service),
) -> ApiResponse[ScanBody]:
    """执行（或读取已落库的）指定策略扫描。"""
    signals = service.scan(name, date_)
    return ApiResponse(
        message="ok",
        body=ScanBody(strategy=name, date=date_, signals=signals),
    )


@router.get("/strategies/{name}/signals", response_model=ApiResponse[SignalsBody])
def get_signals(
    name: str,
    start: date | None = Query(None, description="起始日（含，YYYY-MM-DD）"),
    end: date | None = Query(None, description="结束日（含，YYYY-MM-DD）"),
    service: StrategyService = Depends(get_strategy_service),
) -> ApiResponse[SignalsBody]:
    """查询历史信号。"""
    signals = service.get_signals(name, start, end)
    return ApiResponse(
        message="ok",
        body=SignalsBody(strategy=name, signals=signals),
    )
