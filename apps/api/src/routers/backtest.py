"""回测路由：发起 / 查询 / 衰减曲线。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from schemas.backtest import BacktestRunBody, BacktestRunRequest, DecayBody
from schemas.common import ApiResponse
from services.backtest_service import BacktestService

router = APIRouter(tags=["backtest"])


def get_backtest_service(request: Request) -> BacktestService:
    """从应用状态取回测服务实例。"""
    return request.app.state.backtest_service


@router.post("/backtest/runs", response_model=ApiResponse[BacktestRunBody])
def create_run(
    payload: BacktestRunRequest,
    service: BacktestService = Depends(get_backtest_service),
) -> ApiResponse[BacktestRunBody]:
    """发起回测（同步执行），返回任务与完整报告。"""
    run = service.create_run(payload)
    return ApiResponse(message="ok", body=run)


@router.get("/backtest/runs/{run_id}", response_model=ApiResponse[BacktestRunBody])
def get_run(
    run_id: str,
    service: BacktestService = Depends(get_backtest_service),
) -> ApiResponse[BacktestRunBody]:
    """查询回测结果。"""
    run = service.get_run(run_id)
    return ApiResponse(message="ok", body=run)


@router.get("/backtest/decay", response_model=ApiResponse[DecayBody])
def get_decay(
    strategy: str = Query(..., description="策略名"),
    window: int = Query(20, description="滚动窗口长度（交易日）"),
    hold_days: int = Query(1, description="衰减监测用的持有期（交易日）"),
    start: date | None = Query(None, description="起始日（YYYY-MM-DD）"),
    end: date | None = Query(None, description="结束日（YYYY-MM-DD）"),
    service: BacktestService = Depends(get_backtest_service),
) -> ApiResponse[DecayBody]:
    """查询策略衰减曲线（滚动窗口胜率）。"""
    body = service.get_decay(strategy, window, hold_days, start, end)
    return ApiResponse(message="ok", body=body)
