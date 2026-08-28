"""健康检查路由。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from market import MARKET_TIMEZONE
from schemas.common import ApiResponse
from schemas.health import HealthBody

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[HealthBody])
def health() -> ApiResponse[HealthBody]:
    """存活探针：返回服务状态与当前市场时区时间。"""
    return ApiResponse(
        message="ok",
        body=HealthBody(
            status="ok",
            time=datetime.now(MARKET_TIMEZONE).isoformat(),
        ),
    )
