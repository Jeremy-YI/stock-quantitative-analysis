"""通达信价格比例：个股 ×100、场内基金（ETF/LOF）×1000。

背景：510300 收盘 4.679 在 .day 里存的是 4679，旧代码统一 /100 会读成 46.79，
ETF 的绝对价格全部偏大 10 倍（比率类指标不受影响，但涉及价格的判断会错）。
"""

from __future__ import annotations

import struct

import pytest

from datasource.tdx import (
    is_fund,
    parse_day_file,
    parse_records,
    resolve_price_divisor,
    symbol_from_path,
)

_STRUCT = struct.Struct("<IIIIIfII")


def _bar(date_int: int, close_raw: int) -> bytes:
    return _STRUCT.pack(date_int, close_raw, close_raw, close_raw, close_raw, 1.0e8, 100, 0)


@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("600519", False),  # 沪市个股
        ("688111", False),  # 科创板个股
        ("000001", False),  # 深市个股
        ("110059", False),  # 可转债
        ("510300", True),   # 沪深300ETF
        ("512480", True),   # 半导体ETF
        ("588200", True),   # 科创板 ETF
        ("159915", True),   # 深市 ETF
        ("161725", True),   # LOF
    ],
)
def test_is_fund(symbol: str, expected: bool) -> None:
    assert is_fund(symbol) is expected


def test_resolve_price_divisor() -> None:
    assert resolve_price_divisor("600519") == 100.0
    assert resolve_price_divisor("510300") == 1000.0


def test_symbol_from_path() -> None:
    assert symbol_from_path("/data/sh/lday/sh510300.day") == "510300"
    assert symbol_from_path("sz159915.day") == "159915"


def test_parse_records_uses_given_divisor() -> None:
    data = _bar(20260828, 4679)
    stock = parse_records(data)  # 默认个股口径
    fund = parse_records(data, 1000.0)
    assert stock[0]["close"] == pytest.approx(46.79)
    assert fund[0]["close"] == pytest.approx(4.679)


def test_parse_day_file_autodetects_fund(tmp_path) -> None:
    """按文件名判定：ETF 走 /1000，个股走 /100，调用方不用操心。"""
    etf = tmp_path / "sh510300.day"
    etf.write_bytes(_bar(20260827, 4700) + _bar(20260828, 4679))
    df = parse_day_file(etf)
    assert df["close"].iloc[-1] == pytest.approx(4.679)

    stock = tmp_path / "sh600519.day"
    stock.write_bytes(_bar(20260828, 145000))
    df2 = parse_day_file(stock)
    assert df2["close"].iloc[-1] == pytest.approx(1450.0)
