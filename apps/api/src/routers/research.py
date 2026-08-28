"""因子研究路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from schemas.common import ApiResponse
from schemas.research import ResearchSummary
from services.research_service import ResearchService

router = APIRouter(tags=["research"])


def get_research_service(request: Request) -> ResearchService:
    """从应用状态取因子研究服务实例。"""
    return request.app.state.research_service


@router.get("/research", response_model=ApiResponse[ResearchSummary])
def summary(
    service: ResearchService = Depends(get_research_service),
) -> ApiResponse[ResearchSummary]:
    """因子研究汇总（单因子超额表 / 交叉矩阵 / regime 分层）。"""
    return ApiResponse(message="ok", body=service.summary())
