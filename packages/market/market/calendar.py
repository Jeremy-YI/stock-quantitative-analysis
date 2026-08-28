"""A股交易日历（阶段 1 简化版）。

阶段 1：只排除周末。法定节假日休市表（春节/国庆等）后续通过配置文件接入。
所有行情时间一律用 Asia/Shanghai 时区，禁止用本地时区或 UTC。
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

MARKET_TIMEZONE = ZoneInfo("Asia/Shanghai")


def is_trading_day(day: date) -> bool:
    """判断某日是否为 A股交易日。

    阶段 1 实现：工作日（周一~周五）即视为交易日。
    TODO: 接入法定节假日与调休补班日历，覆盖春节/国庆等长假休市。
    """
    return day.weekday() < 5
