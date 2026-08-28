"""stock-backtest：A股回测引擎（信号验证 / 组合回测 / 统计 / 策略衰减）。

统一入口 ``BacktestEngine``；纯函数层（execution / forward / stats / portfolio）
可独立单测。结果模型见 ``backtest.models``，配置见 ``backtest.config``。
"""

from __future__ import annotations

from backtest.config import (
    DEFAULT_HOLD_DAYS,
    BacktestConfig,
    CostConfig,
    PortfolioConfig,
    default_config,
)
from backtest.engine import (
    BacktestEngine,
    CandlesProvider,
    DictCandlesProvider,
    classify_board,
)
from backtest.models import (
    BoardResult,
    DecayPoint,
    DecaySeries,
    EquityPoint,
    HoldReturn,
    PortfolioReport,
    StrategyResult,
    VerificationReport,
)

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BoardResult",
    "CandlesProvider",
    "CostConfig",
    "DEFAULT_HOLD_DAYS",
    "DecayPoint",
    "DecaySeries",
    "DictCandlesProvider",
    "EquityPoint",
    "HoldReturn",
    "PortfolioConfig",
    "PortfolioReport",
    "StrategyResult",
    "VerificationReport",
    "classify_board",
    "default_config",
]
