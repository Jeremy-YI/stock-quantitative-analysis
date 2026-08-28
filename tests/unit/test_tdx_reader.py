"""通达信 hsjday 数据源单元测试：二进制解析 + 市场判定。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from datasource.tdx import parse_records, resolve_market, resolve_symbol_path
from tests.helpers import build_day_bytes, make_daily_records


def test_parse_records_decodes_single_record():
    data = build_day_bytes(
        [
            {
                "date": date(2026, 8, 27),
                "open": 10.0,
                "high": 10.5,
                "low": 9.8,
                "close": 10.2,
                "volume": 10000,
                "amount": 1234567.5,
            }
        ]
    )
    records = parse_records(data)

    assert len(records) == 1
    row = records[0]
    assert row["date"] == date(2026, 8, 27)
    assert row["open"] == pytest.approx(10.0)
    assert row["high"] == pytest.approx(10.5)
    assert row["low"] == pytest.approx(9.8)
    assert row["close"] == pytest.approx(10.2)
    assert row["volume"] == 10000
    assert row["amount"] == pytest.approx(1234567.5)


def test_parse_records_ignores_trailing_partial_record():
    full = build_day_bytes(make_daily_records(1))
    records = parse_records(full + b"\x00\x01")  # 尾部多出 2 字节，不足一条记录
    assert len(records) == 1


def test_parse_records_empty_bytes_returns_empty():
    assert parse_records(b"") == []


def test_resolve_market_by_prefix():
    assert resolve_market("600519") == "sh"
    assert resolve_market("688001") == "sh"
    assert resolve_market("000001") == "sz"
    assert resolve_market("300750") == "sz"
    assert resolve_market("430017") == "bj"


def test_resolve_symbol_path_layout():
    root = Path("/data/hsjday")
    assert resolve_symbol_path(root, "600519") == Path("/data/hsjday/sh/lday/sh600519.day")
    assert resolve_symbol_path(root, "000001") == Path("/data/hsjday/sz/lday/sz000001.day")
    assert resolve_symbol_path(root, "430017") == Path("/data/hsjday/bj/lday/bj430017.day")
