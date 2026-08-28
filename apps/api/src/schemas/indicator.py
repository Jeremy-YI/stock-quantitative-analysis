"""MACD 指标契约。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

# 请求参数校验：symbol 必须是 6 位数字（A股代码），否则 FastAPI 自动返回 422
SYMBOL_PATTERN = r"^\d{6}$"


class MacdPoint(BaseModel):
    """单根 K 线对应的 MACD 数据点。数值统一保留 4 位小数。"""

    date: date
    close: float
    dif: float
    dea: float
    macd: float


class MacdBody(BaseModel):
    """MACD 指标响应体。"""

    symbol: str
    series: list[MacdPoint]


class MacdQuery(BaseModel):
    """GET /indicators/macd 的查询参数。"""

    symbol: str = Field(pattern=SYMBOL_PATTERN)
    start: date | None = None
    end: date | None = None
