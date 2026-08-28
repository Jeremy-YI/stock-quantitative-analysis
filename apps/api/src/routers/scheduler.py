"""调度器路由：任务列表 / 执行历史 / 手动触发。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from errors import UnknownJobError
from schemas.common import ApiResponse
from schemas.scheduler import (
    JobListBody,
    RunListBody,
    TriggerBody,
    TriggerRequest,
)
from services.scheduler_service import SchedulerService

router = APIRouter(tags=["scheduler"])


def get_scheduler_service(request: Request) -> SchedulerService:
    """从应用状态取调度器服务实例。"""
    return request.app.state.scheduler_service


@router.get("/scheduler/jobs", response_model=ApiResponse[JobListBody])
def list_jobs(
    service: SchedulerService = Depends(get_scheduler_service),
) -> ApiResponse[JobListBody]:
    """任务列表（含 cron、下次执行时间、上次状态、耗时）。"""
    return ApiResponse(
        message="ok",
        body=JobListBody(jobs=service.list_jobs()),
    )


@router.get("/scheduler/runs", response_model=ApiResponse[RunListBody])
def list_runs(
    job: str | None = Query(None, description="任务名（缺省查全部）"),
    limit: int = Query(50, ge=1, le=500, description="返回条数上限"),
    service: SchedulerService = Depends(get_scheduler_service),
) -> ApiResponse[RunListBody]:
    """执行历史（时间倒序）。"""
    return ApiResponse(
        message="ok",
        body=RunListBody(runs=service.list_runs(job=job, limit=limit)),
    )


@router.post("/scheduler/jobs/{name}/trigger", response_model=ApiResponse[TriggerBody])
def trigger_job(
    name: str,
    payload: TriggerRequest | None = None,
    service: SchedulerService = Depends(get_scheduler_service),
) -> ApiResponse[TriggerBody]:
    """手动触发一次任务（同步执行，返回本次执行记录）。"""
    trigger = payload.trigger if payload else "manual"
    try:
        run = service.trigger(name, trigger=trigger)
    except KeyError as exc:
        raise UnknownJobError(f"任务 {name} 不存在") from exc
    return ApiResponse(
        message="ok",
        body=TriggerBody(job_name=name, trigger=trigger, run=run),
    )
