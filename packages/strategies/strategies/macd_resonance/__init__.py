"""MACD 月周共振策略模块。"""

from strategies.macd_resonance.config import MacdResonanceConfig, default_config
from strategies.macd_resonance.strategy import (
    DESCRIPTION,
    LABEL,
    NAME,
    SIGNAL_TYPE,
    TARGET_KINDS,
    scan,
)

__all__ = [
    "DESCRIPTION",
    "LABEL",
    "NAME",
    "SIGNAL_TYPE",
    "TARGET_KINDS",
    "MacdResonanceConfig",
    "default_config",
    "scan",
]
