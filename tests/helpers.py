"""测试公共工具。"""

from __future__ import annotations

import struct
from datetime import date

# .day 记录格式（与 datasource.tdx.reader 保持一致）
_STRUCT = struct.Struct("<IIIIIfII")


def build_day_bytes(
    records: list[dict],
) -> bytes:
    """把记录字典列表编码成 .day 文件字节，供测试构造临时数据文件。

    Args:
        records: 每个元素含 date/open/high/low/close/volume/amount 键。
            date 为 datetime.date，价格单位为元，volume 为手，amount 为元。
    """
    buf = bytearray()
    for r in records:
        buf += _STRUCT.pack(
            int(r["date"].strftime("%Y%m%d")),
            round(r["open"] * 100),
            round(r["high"] * 100),
            round(r["low"] * 100),
            round(r["close"] * 100),
            float(r["amount"]),
            int(r["volume"]),
            0,
        )
    return bytes(buf)


def make_daily_records(
    n: int = 35, start: date = date(2026, 1, 2), base_close: float = 10.0
) -> list[dict]:
    """生成 n 根连续「工作日」的日线记录（价格单调微涨，便于断言）。"""
    from datetime import timedelta

    records: list[dict] = []
    day = start
    while len(records) < n:
        if day.weekday() < 5:
            close = base_close + len(records) * 0.1
            records.append(
                {
                    "date": day,
                    "open": close - 0.05,
                    "high": close + 0.2,
                    "low": close - 0.2,
                    "close": close,
                    "volume": 10000 + len(records),
                    "amount": close * 100000,
                }
            )
        day += timedelta(days=1)
    return records
