"""A股交易日历单元测试：节假日表 + 交易日序列 + 平移。

阶段 4 修复阶段 1 的「工作日=交易日」近似，锁死几个关键长假休市日。
"""

from __future__ import annotations

from datetime import date

from market import (
    HOLIDAYS,
    is_trading_day,
    shift_trading_day,
    trading_days,
)


def test_weekend_not_trading():
    assert is_trading_day(date(2026, 8, 29)) is False  # 周六
    assert is_trading_day(date(2026, 8, 30)) is False  # 周日


def test_spring_festival_not_trading():
    # 2026 春节：除夕 02-16（周一）起休市
    assert is_trading_day(date(2026, 2, 16)) is False
    assert is_trading_day(date(2026, 2, 17)) is False
    assert is_trading_day(date(2026, 2, 18)) is False
    # 节后复工日（数据里 02-24 周二应恢复交易，02-23 在表内休市）
    assert is_trading_day(date(2026, 2, 24)) is True


def test_national_day_not_trading():
    # 国庆长假
    assert is_trading_day(date(2025, 10, 1)) is False
    assert is_trading_day(date(2025, 10, 7)) is False
    # 节后首个交易日
    assert is_trading_day(date(2025, 10, 9)) is True


def test_regular_weekday_is_trading():
    assert is_trading_day(date(2026, 8, 27)) is True  # 周四（数据末日）


def test_holidays_cover_2020_to_2026():
    """节假日表至少覆盖 2020-2026 每年都有休市日。"""
    for year in range(2020, 2027):
        year_holidays = [d for d in HOLIDAYS if d.year == year]
        assert year_holidays, f"{year} 年无节假日记录"


def test_trading_days_sequence():
    # 2026-08-24（周一）~ 2026-08-28（周五）共 5 个交易日
    days = trading_days(date(2026, 8, 24), date(2026, 8, 28))
    assert len(days) == 5
    assert days[0] == date(2026, 8, 24)
    assert days[-1] == date(2026, 8, 28)


def test_trading_days_empty_when_reversed():
    assert trading_days(date(2026, 8, 28), date(2026, 8, 24)) == []


def test_shift_trading_day_forward():
    # 周一 + 1 = 周二
    assert shift_trading_day(date(2026, 8, 24), 1) == date(2026, 8, 25)
    # 周五 + 1 = 下周一（跳过周末）
    assert shift_trading_day(date(2026, 8, 28), 1) == date(2026, 8, 31)


def test_shift_trading_day_backward():
    assert shift_trading_day(date(2026, 8, 25), -1) == date(2026, 8, 24)
    # 周一 - 1 = 上周五
    assert shift_trading_day(date(2026, 8, 24), -1) == date(2026, 8, 21)


def test_shift_trading_day_skip_holiday():
    # 2025-09-30（周二）是国庆前最后交易日，+1 = 2025-10-09（节后首日）
    assert shift_trading_day(date(2025, 9, 30), 1) == date(2025, 10, 9)
