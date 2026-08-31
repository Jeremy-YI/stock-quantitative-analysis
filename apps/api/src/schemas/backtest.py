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
    regime_filter: bool = Field(
        False, description="是否启用市场环境（regime）过滤，只在允许状态下开仓"
    )


class BacktestRunBody(BaseModel):
    """一次回测任务的完整结果。"""

    run_id: str
    strategy: str | None
    start: date
    end: date
    mode: str
    report: BacktestReport


class BacktestJob(BaseModel):
    """异步回测任务的状态（POST 立即返回，GET 轮询结果）。

    回测是全市场逐日扫描的重活（单策略约 30s/交易日），同步执行会让前端
    fetch 超时并拿到 500 —— 所以发起后立刻返回 run_id + 状态，结果好了再查。
    """

    run_id: str
    status: str          # queued / running / done / failed
    strategy: str | None
    start: date
    end: date
    error: str | None = None
    report: BacktestReport | None = None


class DecayBody(BaseModel):
    """策略衰减曲线响应体。"""

    strategy: str
    window: int
    hold_days: int
    points: list[DecayPoint]
