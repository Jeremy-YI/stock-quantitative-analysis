"""指标路由。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from schemas.common import ApiResponse
from schemas.indicator import (
    CandlesBody,
    KdjBody,
    MacdBody,
    PricingLinesBody,
    RsiBody,
    VolumeBody,
)
from services.indicator_service import IndicatorService
from services.stock_meta_service import StockMetaService

router = APIRouter(tags=["indicators"])


def get_indicator_service(request: Request) -> IndicatorService:
    """从应用状态取 service 实例（测试时可注入 fake repository）。"""
    return request.app.state.service


def get_stock_meta_service(request: Request) -> StockMetaService:
    """股票名称 / ST 服务。"""
    return request.app.state.stock_meta_service


def _symbol_query() -> str:
    """6 位 A股代码查询参数（复用同一个校验模式）。"""
    return Query(pattern=r"^\d{6}$", description="6 位 A股代码")


def _start_query() -> date | None:
    return Query(None, description="起始日（含，YYYY-MM-DD）")


def _end_query() -> date | None:
    return Query(None, description="结束日（含，YYYY-MM-DD）")


def _limit_query() -> int | None:
    """只返回最后 N 个点（指标仍按全量历史计算，只截展示窗口）。

    图上默认给近 1~2 个月（约 22 / 44 个交易日），用户放大再要更长。
    """
    return Query(None, ge=5, le=2000, description="只返回最后 N 个点（默认全部）")


@router.get("/indicators/candles", response_model=ApiResponse[CandlesBody])
def get_candles(
    symbol: str = _symbol_query(),
    start: date | None = _start_query(),
    end: date | None = _end_query(),
    limit: int | None = _limit_query(),
    service: IndicatorService = Depends(get_indicator_service),
    meta: StockMetaService = Depends(get_stock_meta_service),
) -> ApiResponse[CandlesBody]:
    """日 K 线（个股详情页画蜡烛图 + 叠加买点用）。"""
    body = service.get_candles(symbol, start, end, limit, name=meta.name(symbol))
    return ApiResponse(message="ok", body=body)


@router.get("/indicators/macd", response_model=ApiResponse[MacdBody])
def get_macd(
    symbol: str = _symbol_query(),
    start: date | None = _start_query(),
    end: date | None = _end_query(),
    limit: int | None = _limit_query(),
    service: IndicatorService = Depends(get_indicator_service),
) -> ApiResponse[MacdBody]:
    """计算指定标的的 MACD 指标序列。"""
    body = service.get_macd(symbol, start, end, limit)
    return ApiResponse(message="ok", body=body)


@router.get("/indicators/pricing-lines", response_model=ApiResponse[PricingLinesBody])
def get_pricing_lines(
    symbol: str = _symbol_query(),
    start: date | None = _start_query(),
    end: date | None = _end_query(),
    limit: int | None = _limit_query(),
    service: IndicatorService = Depends(get_indicator_service),
) -> ApiResponse[PricingLinesBody]:
    """计算指定标的的三条定价线序列（生命线 / 阴量定价线 / 进攻K防线）。"""
    body = service.get_pricing_lines(symbol, start, end, limit)
    return ApiResponse(message="ok", body=body)


@router.get("/indicators/kdj", response_model=ApiResponse[KdjBody])
def get_kdj(
    symbol: str = _symbol_query(),
    start: date | None = _start_query(),
    end: date | None = _end_query(),
    limit: int | None = _limit_query(),
    service: IndicatorService = Depends(get_indicator_service),
) -> ApiResponse[KdjBody]:
    """计算指定标的的 KDJ 指标序列。"""
    body = service.get_kdj(symbol, start, end, limit)
    return ApiResponse(message="ok", body=body)


@router.get("/indicators/rsi", response_model=ApiResponse[RsiBody])
def get_rsi(
    symbol: str = _symbol_query(),
    start: date | None = _start_query(),
    end: date | None = _end_query(),
    limit: int | None = _limit_query(),
    service: IndicatorService = Depends(get_indicator_service),
) -> ApiResponse[RsiBody]:
    """计算指定标的的 RSI 指标序列。"""
    body = service.get_rsi(symbol, start, end, limit)
    return ApiResponse(message="ok", body=body)


@router.get("/indicators/volume", response_model=ApiResponse[VolumeBody])
def get_volume(
    symbol: str = _symbol_query(),
    start: date | None = _start_query(),
    end: date | None = _end_query(),
    limit: int | None = _limit_query(),
    service: IndicatorService = Depends(get_indicator_service),
) -> ApiResponse[VolumeBody]:
    """计算指定标的的量能指标序列。"""
    body = service.get_volume(symbol, start, end, limit)
    return ApiResponse(message="ok", body=body)
