"""A股交易日历（阶段 4：内置节假日表，覆盖 2020-01-01 起）。

阶段 1 只有「工作日=交易日」的近似。阶段 4 修正为：

    - 排除周末（周一~周五才可能是交易日）；
    - 排除法定休市日（``market.holidays.HOLIDAYS``，由 hsjday 实际交易日反推，
      见 scripts/make_trading_calendar.py）。

数据末日之后的日期不在节假日表内，``is_trading_day`` 对它们回退到
「工作日=交易日」近似（未来节假日未知，属于合理降级）。

所有行情时间一律用 Asia/Shanghai 时区，禁止用本地时区或 UTC。
"""

from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from market.holidays import HOLIDAYS

MARKET_TIMEZONE = ZoneInfo("Asia/Shanghai")


def is_trading_day(day: date) -> bool:
    """判断某日是否为 A股交易日（排除周末 + 法定休市日）。"""
    if day.weekday() >= 5:
        return False
    return day not in HOLIDAYS


def trading_days(start: date, end: date) -> list[date]:
    """返回 [start, end] 区间内（闭区间）的交易日列表，按时间升序。"""
    if end < start:
        return []
    out: list[date] = []
    d = start
    while d <= end:
        if is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def shift_trading_day(day: date, n: int) -> date:
    """返回 ``day`` 之后（n>0）或之前（n<0）第 ``|n|`` 个交易日。

    n = 0 时原样返回 ``day``（不校验其是否为交易日）。
    未来方向若超出节假日表覆盖范围，回退到「工作日=交易日」近似。
    """
    if n == 0:
        return day
    step = 1 if n > 0 else -1
    remaining = abs(n)
    d = day
    while remaining > 0:
        d += timedelta(days=step)
        if is_trading_day(d):
            remaining -= 1
    return d
