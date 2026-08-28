"""概览页路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from schemas.common import ApiResponse
from schemas.dashboard import DashboardOverview
from services.dashboard_service import DashboardService

router = APIRouter(tags=["dashboard"])


def get_dashboard_service(request: Request) -> DashboardService:
    """从应用状态取概览页服务实例。"""
    return request.app.state.dashboard_service


@router.get("/dashboard/overview", response_model=ApiResponse[DashboardOverview])
def overview(
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[DashboardOverview]:
    """概览页聚合数据（各策略信号数/选择性/超额胜率 + 市场基线 + 调度状态）。"""
    return ApiResponse(message="ok", body=service.overview())
