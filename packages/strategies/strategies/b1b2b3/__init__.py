"""B1/B2/B3 策略模块。"""

from strategies.b1b2b3.config import B1B2B3Config, default_config
from strategies.b1b2b3.strategy import DESCRIPTION, LABEL, NAME, SCORE, TARGET_KINDS, scan

__all__ = [
    "B1B2B3Config",
    "DESCRIPTION",
    "LABEL",
    "NAME",
    "SCORE",
    "TARGET_KINDS",
    "default_config",
    "scan",
]
