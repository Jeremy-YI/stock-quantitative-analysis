"""MACD 水下多头 + 极缩量（washout）策略模块。"""

from strategies.macd_volume_washout.config import (
    MacdVolumeWashoutConfig,
    default_config,
)
from strategies.macd_volume_washout.strategy import (
    DESCRIPTION,
    LABEL,
    NAME,
    SIGNAL_TYPE,
    TARGET_KINDS,
    evaluate,
    scan,
)

__all__ = [
    "DESCRIPTION",
    "LABEL",
    "NAME",
    "SIGNAL_TYPE",
    "TARGET_KINDS",
    "MacdVolumeWashoutConfig",
    "default_config",
    "evaluate",
    "scan",
]
