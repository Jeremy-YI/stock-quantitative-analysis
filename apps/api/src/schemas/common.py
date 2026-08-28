"""通用响应包装：{ message, body }。"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应结构。message 为语义串，body 为业务数据。"""

    message: str
    body: T | None = None
