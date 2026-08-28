"""双底反弹策略模块。"""

from strategies.double_bottom.config import DoubleBottomConfig, default_config
from strategies.double_bottom.strategy import (
    DESCRIPTION,
    NAME,
    SIGNAL_TYPE,
    TARGET_KINDS,
    scan,
    swing_lows,
)

__all__ = [
    "DESCRIPTION",
    "NAME",
    "SIGNAL_TYPE",
    "TARGET_KINDS",
    "DoubleBottomConfig",
    "default_config",
    "scan",
    "swing_lows",
]
