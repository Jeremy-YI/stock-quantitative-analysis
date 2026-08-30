"""单针下30（PIN30）策略模块。"""

from strategies.pin30.config import Pin30Config, default_config
from strategies.pin30.strategy import DESCRIPTION, LABEL, NAME, SCORE, TARGET_KINDS, scan

__all__ = [
    "DESCRIPTION",
    "LABEL",
    "NAME",
    "SCORE",
    "TARGET_KINDS",
    "Pin30Config",
    "default_config",
    "scan",
]
