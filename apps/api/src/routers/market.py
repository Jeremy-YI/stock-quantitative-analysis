"""市场资讯路由（最新消息 / 事件日历）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from schemas.common import ApiResponse
from schemas.market import EventsBody, NewsBody
from services.market_service import MarketService

router = APIRouter(tags=["market"])


def get_market_service(request: Request) -> MarketService:
    return request.app.state.market_service


@router.get("/news", response_model=ApiResponse[NewsBody])
def get_news(service: MarketService = Depends(get_market_service)) -> ApiResponse[NewsBody]:
    """最新消息（财经日报式：标题 + 影响评级 + 未来导向）。"""
    return ApiResponse(message="ok", body=service.get_news())


@router.get("/events", response_model=ApiResponse[EventsBody])
def get_events(service: MarketService = Depends(get_market_service)) -> ApiResponse[EventsBody]:
    """事件日历（关键会议 / 数据 / 财报）。"""
    return ApiResponse(message="ok", body=service.get_events())
