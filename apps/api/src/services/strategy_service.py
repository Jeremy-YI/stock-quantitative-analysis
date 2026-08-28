"""策略服务。

职责：按名取策略 → 调扫描器取 candles → 跑策略 scan → 落库 → 返回信号。
不碰 HTTP，不读文件（通过扫描器），保持纯业务逻辑可单测。
"""

from __future__ import annotations

from datetime import date

from errors import UnknownStrategyError
from repositories.scan_result_repository import ScanResultRepository
from schemas.strategy import StrategyInfo
from strategies import REGISTRY
from strategies.filters import filter_for_kinds
from strategies.scanner import Scanner
from strategies.signal import Signal


class StrategyService:
    """策略扫描与查询服务。"""

    def __init__(
        self,
        scanner: Scanner,
        repository: ScanResultRepository,
    ) -> None:
        self._scanner = scanner
        self._repository = repository

    def list_strategies(self) -> list[StrategyInfo]:
        """返回全部可用策略及其配置说明。"""
        infos: list[StrategyInfo] = []
        for name, mod in REGISTRY.items():
            cfg = mod.default_config()
            infos.append(
                StrategyInfo(
                    name=name,
                    description=mod.DESCRIPTION,
                    config=cfg.model_dump(),
                    config_schema=type(cfg).model_json_schema(),
                )
            )
        return infos

    def scan(self, name: str, as_of: date) -> list[Signal]:
        """执行一次扫描（或读当日已落库结果）并落库。"""
        mod = self._get_strategy(name)
        # 按策略声明的目标宇宙过滤标的（个股策略 vs ETF 策略）
        candles = self._scanner.load_candles(
            as_of, filter_config=filter_for_kinds(mod.TARGET_KINDS)
        )
        signals = mod.scan(candles, as_of)
        self._repository.save(name, signals)
        return signals

    def get_signals(
        self, name: str, start: date | None = None, end: date | None = None
    ) -> list[Signal]:
        """查询历史信号。"""
        self._get_strategy(name)
        return self._repository.get_signals(name, start, end)

    def _get_strategy(self, name: str):
        if name not in REGISTRY:
            raise UnknownStrategyError(f"策略 {name} 不存在")
        return REGISTRY[name]
