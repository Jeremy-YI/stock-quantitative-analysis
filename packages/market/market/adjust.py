"""复权模式。

阶段 1：通达信 hsjday .day 文件为不复权原始数据，复权因子尚未接入。
DEFAULT_ADJUST_MODE 仍定为「前复权」，作为回测统一口径的默认约定。
"""

from __future__ import annotations

from enum import Enum


class AdjustMode(str, Enum):
    """复权模式枚举。"""

    FORWARD = "forward"  # 前复权
    BACKWARD = "backward"  # 后复权
    NONE = "none"  # 不复权


DEFAULT_ADJUST_MODE = AdjustMode.FORWARD
