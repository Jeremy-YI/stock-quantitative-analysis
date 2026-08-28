"""A股市场业务规则单元测试：涨跌停 + 交易日历 + 复权。"""

from __future__ import annotations

from datetime import date

from market import DEFAULT_ADJUST_MODE, MARKET_TIMEZONE, AdjustMode, get_price_limit, is_trading_day


def test_price_limit_rules():
    assert get_price_limit("600519").up == 10.0  # 主板
    assert get_price_limit("600519").down == -10.0
    assert get_price_limit("300750").up == 20.0  # 创业板
    assert get_price_limit("688001").up == 20.0  # 科创板
    assert get_price_limit("430017").up == 30.0  # 北交所
    assert get_price_limit("600519", is_st=True).up == 5.0  # ST
    assert get_price_limit("600519", is_st=True).down == -5.0


def test_is_trading_day_weekend():
    assert is_trading_day(date(2026, 8, 28)) is True  # 周五
    assert is_trading_day(date(2026, 8, 29)) is False  # 周六
    assert is_trading_day(date(2026, 8, 30)) is False  # 周日


def test_market_timezone_is_shanghai():
    assert str(MARKET_TIMEZONE) == "Asia/Shanghai"


def test_default_adjust_mode_is_forward():
    assert DEFAULT_ADJUST_MODE == AdjustMode.FORWARD
