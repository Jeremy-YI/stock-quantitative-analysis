"""ETF 连续吸筹策略模块。"""

from strategies.etf_accumulation.config import EtfAccumulationConfig, default_config
from strategies.etf_accumulation.strategy import (
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
    "EtfAccumulationConfig",
    "default_config",
    "scan",
]
