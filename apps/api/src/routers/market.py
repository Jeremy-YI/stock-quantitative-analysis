"""市场资讯路由（最新消息 / 事件日历）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from schemas.common import ApiResponse
from schemas.market import EventDetailBody, EventsBody, NewsBody, NewsDetailBody
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


@router.get("/news/{news_id}", response_model=ApiResponse[NewsDetailBody])
def get_news_detail(
    news_id: str,
    service: MarketService = Depends(get_market_service),
) -> ApiResponse[NewsDetailBody]:
    """单条消息详情（全文 + 相关标的 + 相关消息）。"""
    body = service.get_news_detail(news_id)
    if body is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    return ApiResponse(message="ok", body=body)


@router.get("/events/{event_id}", response_model=ApiResponse[EventDetailBody])
def get_event_detail(
    event_id: str,
    service: MarketService = Depends(get_market_service),
) -> ApiResponse[EventDetailBody]:
    """单个事件详情（说明 + 历史数据）。"""
    body = service.get_event_detail(event_id)
    if body is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    return ApiResponse(message="ok", body=body)
