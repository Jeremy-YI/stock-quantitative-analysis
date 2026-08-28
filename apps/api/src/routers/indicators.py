"""指标路由。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from schemas.common import ApiResponse
from schemas.indicator import MacdBody
from services.indicator_service import IndicatorService

router = APIRouter(tags=["indicators"])


def get_indicator_service(request: Request) -> IndicatorService:
    """从应用状态取 service 实例（测试时可注入 fake repository）。"""
    return request.app.state.service


@router.get("/indicators/macd", response_model=ApiResponse[MacdBody])
def get_macd(
    symbol: str = Query(pattern=r"^\d{6}$", description="6 位 A股代码"),
    start: date | None = Query(None, description="起始日（含，YYYY-MM-DD）"),
    end: date | None = Query(None, description="结束日（含，YYYY-MM-DD）"),
    service: IndicatorService = Depends(get_indicator_service),
) -> ApiResponse[MacdBody]:
    """计算指定标的的 MACD 指标序列。"""
    body = service.get_macd(symbol, start, end)
    return ApiResponse(message="ok", body=body)
