"""板块资金流路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from schemas.common import ApiResponse
from schemas.sector import SectorFlowBody
from services.sector_service import SectorService

router = APIRouter(tags=["sectors"])


def get_sector_service(request: Request) -> SectorService:
    """从应用状态取 sector service（测试时可注入 fake）。"""
    return request.app.state.sector_service


@router.get("/sectors/flow", response_model=ApiResponse[SectorFlowBody])
def sector_flow(
    days: str = Query("即时", description="窗口：即时/3日排行/5日排行/10日排行/20日排行"),
    service: SectorService = Depends(get_sector_service),
) -> ApiResponse[SectorFlowBody]:
    """板块资金流：top20 净流入 + top20 净流出。"""
    return ApiResponse(message="ok", body=service.sector_flow(days))
