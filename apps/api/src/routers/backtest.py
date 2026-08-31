"""回测路由：发起 / 查询 / 衰减曲线。"""

from __future__ import annotations

import threading
import traceback
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from schemas.backtest import BacktestJob, BacktestRunRequest, DecayBody
from schemas.common import ApiResponse
from services.backtest_service import BacktestService

router = APIRouter(tags=["backtest"])


def get_backtest_service(request: Request) -> BacktestService:
    """从应用状态取回测服务实例。"""
    return request.app.state.backtest_service


@router.post("/backtest/runs", response_model=ApiResponse[BacktestJob])
def create_run(
    payload: BacktestRunRequest,
    request: Request,
    service: BacktestService = Depends(get_backtest_service),
) -> ApiResponse[BacktestJob]:
    """发起回测（异步执行）。

    回测是全市场逐日扫描的重活（单策略约 30s/交易日），同步跑会让前端超时 500。
    所以这里立刻返回 run_id + status，后台线程算完后结果可查询。
    """
    store = request.app.state.backtest_jobs
    run_id = service.create_run_async(payload)

    # 占位：finish_run 要据此重建请求
    store[run_id] = {
        "run_id": run_id,
        "status": "queued",
        "strategy": payload.strategy,
        "start": payload.start,
        "end": payload.end,
        "mode": payload.mode,
        "hold_days": payload.hold_days,
        "regime_filter": payload.regime_filter,
        "error": None,
        "report": None,
    }

    def _worker() -> None:
        store[run_id]["status"] = "running"
        try:
            run = service.finish_run(run_id)
            store[run_id].update(status="done", report=run.report, error=None)
            service._repository.save(run)  # noqa: SLF001 - 落库供 get_run 读
        except Exception as exc:  # noqa: BLE001
            store[run_id].update(status="failed", error=str(exc))
            store[run_id]["traceback"] = traceback.format_exc()

    job = store[run_id]
    threading.Thread(target=_worker, daemon=True).start()
    return ApiResponse(message="ok", body=BacktestJob(**job))


@router.get("/backtest/runs/{run_id}", response_model=ApiResponse[BacktestJob])
def get_run(
    run_id: str,
    request: Request,
) -> ApiResponse[BacktestJob]:
    """查询回测任务状态与结果（前端轮询这个）。"""
    store = request.app.state.backtest_jobs
    job = store.get(run_id)
    if job is None:
        raise HTTPException(status_code=404, detail="回测任务不存在")
    return ApiResponse(message="ok", body=BacktestJob(**job))


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
