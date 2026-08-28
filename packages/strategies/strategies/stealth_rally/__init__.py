"""偷涨型策略模块。"""

from strategies.stealth_rally.config import StealthRallyConfig, default_config
from strategies.stealth_rally.strategy import (
    DESCRIPTION,
    NAME,
    SIGNAL_TYPE,
    TARGET_KINDS,
    detect_underwater_double_golden,
    scan,
)

__all__ = [
    "DESCRIPTION",
    "NAME",
    "SIGNAL_TYPE",
    "TARGET_KINDS",
    "StealthRallyConfig",
    "default_config",
    "detect_underwater_double_golden",
    "scan",
]
