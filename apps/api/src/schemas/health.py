"""健康检查响应体。"""

from __future__ import annotations

from pydantic import BaseModel


class HealthBody(BaseModel):
    status: str
    time: str
