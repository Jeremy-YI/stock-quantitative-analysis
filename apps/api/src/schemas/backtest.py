"""回测层契约（发起 / 查询 / 衰减）。"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from backtest.models import BacktestReport, DecayPoint


class BacktestRunRequest(BaseModel):
    """发起回测的请求体。"""

    strategy: str | None = Field(
        None, description="策略名，缺省为全部策略"
    )
    start: date = Field(..., description="回测起始日（YYYY-MM-DD）")
    end: date = Field(..., description="回测结束日（YYYY-MM-DD）")
    mode: str = Field("verify", description="回测模式：verify / portfolio")
    hold_days: list[int] | None = Field(
        None, description="持有期列表，缺省用默认 [1,3,5,10,20]"
    )


class BacktestRunBody(BaseModel):
    """一次回测任务的完整结果。"""

    run_id: str
    strategy: str | None
    start: date
    end: date
    mode: str
    report: BacktestReport


class DecayBody(BaseModel):
    """策略衰减曲线响应体。"""

    strategy: str
    window: int
    hold_days: int
    points: list[DecayPoint]
