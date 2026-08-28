"""指标契约（MACD / KDJ / RSI / 量能）。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

# 请求参数校验：symbol 必须是 6 位数字（A股代码），否则 FastAPI 自动返回 422
SYMBOL_PATTERN = r"^\d{6}$"


# ---------------------------------------------------------------
# MACD
# ---------------------------------------------------------------
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


# ---------------------------------------------------------------
# KDJ
# ---------------------------------------------------------------
class KdjPoint(BaseModel):
    """单根 K 线对应的 KDJ 数据点。"""

    date: date
    close: float
    k: float
    d: float
    j: float


class KdjBody(BaseModel):
    """KDJ 指标响应体。"""

    symbol: str
    series: list[KdjPoint]


# ---------------------------------------------------------------
# RSI
# ---------------------------------------------------------------
class RsiPoint(BaseModel):
    """单根 K 线对应的 RSI 数据点。"""

    date: date
    close: float
    rsi: float


class RsiBody(BaseModel):
    """RSI 指标响应体。"""

    symbol: str
    series: list[RsiPoint]


# ---------------------------------------------------------------
# 量能
# ---------------------------------------------------------------
class VolumePoint(BaseModel):
    """单根 K 线对应的量能数据点。relation 为价量关系中文标签。"""

    date: date
    close: float
    volume: int
    mavol1: float
    mavol2: float
    volume_ratio: float
    relation: str


class VolumeBody(BaseModel):
    """量能指标响应体。"""

    symbol: str
    series: list[VolumePoint]


# ---------------------------------------------------------------
# 查询参数（仅用于文档/校验，路由层用 Query 声明）
# ---------------------------------------------------------------
class MacdQuery(BaseModel):
    """GET /indicators/macd 的查询参数。"""

    symbol: str = Field(pattern=SYMBOL_PATTERN)
    start: date | None = None
    end: date | None = None


class KdjQuery(BaseModel):
    """GET /indicators/kdj 的查询参数。"""

    symbol: str = Field(pattern=SYMBOL_PATTERN)
    start: date | None = None
    end: date | None = None


class RsiQuery(BaseModel):
    """GET /indicators/rsi 的查询参数。"""

    symbol: str = Field(pattern=SYMBOL_PATTERN)
    start: date | None = None
    end: date | None = None


class VolumeQuery(BaseModel):
    """GET /indicators/volume 的查询参数。"""

    symbol: str = Field(pattern=SYMBOL_PATTERN)
    start: date | None = None
    end: date | None = None
