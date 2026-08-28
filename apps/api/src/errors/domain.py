"""领域异常。

约定：service/repository 层抛出领域异常，HTTP 层统一映射成状态码，
禁止在 service 层直接 import HTTP 相关对象。
"""

from __future__ import annotations


class DomainError(Exception):
    """领域异常基类。"""


class SymbolNotFoundError(DomainError):
    """标的代码不存在（映射 HTTP 404）。"""


class InsufficientDataError(DomainError):
    """标的存在但日线数据不足（映射 HTTP 422）。"""


class UnknownStrategyError(DomainError):
    """策略名不存在（映射 HTTP 404）。"""
