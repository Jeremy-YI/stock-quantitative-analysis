"""扫描器集成测试：临时 hsjday 目录 → 过滤 → candles。"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from strategies.filters import FilterConfig
from strategies.scanner import MarketScanner
from tests.helpers import build_day_bytes

AS_OF = date(2026, 8, 27)


def _records(n: int, end: date = AS_OF) -> list[dict]:
    """生成 n 根「以 end 结尾」的工作日日线记录（价格单调微涨）。"""
    days: list[date] = []
    day = end
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    days = list(reversed(days))
    return [
        {
            "date": d,
            "open": 10 + i * 0.1 - 0.05,
            "high": 10 + i * 0.1 + 0.2,
            "low": 10 + i * 0.1 - 0.2,
            "close": 10 + i * 0.1,
            "volume": 10000 + i,
            "amount": (10 + i * 0.1) * 100000,
        }
        for i, d in enumerate(days)
    ]


def _build_market(tmp_path, files: dict[str, list[dict]]) -> None:
    """在 tmp_path 下按 {sh600519.day: records} 建临时 hsjday 目录。"""
    for fname, records in files.items():
        market = fname[:2]
        d = tmp_path / market / "lday"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{fname}.day").write_bytes(build_day_bytes(records))


def test_scanner_filters_out_etf_and_index(tmp_path):
    _build_market(
        tmp_path,
        {
            "sh600519": _records(100),
            "sh510050": _records(100),  # ETF
            "sh000001": _records(100),  # 上证指数
            "sz000001": _records(100),  # 平安银行（个股）
        },
    )
    scanner = MarketScanner(tmp_path, FilterConfig())
    candles = scanner.load_candles(AS_OF)
    assert set(candles.keys()) == {"600519", "000001"}


def test_scanner_respects_min_listing_days(tmp_path):
    _build_market(
        tmp_path,
        {
            "sh600519": _records(100),
            "sh600036": _records(30),  # 上市不足 60 日
        },
    )
    scanner = MarketScanner(tmp_path, FilterConfig(min_listing_days=60))
    candles = scanner.load_candles(AS_OF)
    assert set(candles.keys()) == {"600519"}


def test_scanner_tail_read(tmp_path):
    """lookback 只读尾部：结果与全量读取一致的列与首尾。"""
    records = _records(200)
    _build_market(tmp_path, {"sh600519": records})

    scanner = MarketScanner(tmp_path, FilterConfig(), lookback=50)
    candles = scanner.load_candles(AS_OF)
    df = candles["600519"]
    assert len(df) == 50
    assert df["close"].iloc[-1] == pytest.approx(records[-1]["close"])
    assert df["close"].iloc[0] == pytest.approx(records[-50]["close"])


def test_scanner_returns_full_when_lookback_exceeds_file(tmp_path):
    records = _records(30)
    _build_market(tmp_path, {"sh600519": records})
    # 关闭上市天数过滤，专门验证「lookback 超过文件长度时返回全部」
    scanner = MarketScanner(tmp_path, FilterConfig(min_listing_days=0), lookback=900)
    df = scanner.load_candles(AS_OF)["600519"]
    assert len(df) == 30


def test_scanner_empty_dir(tmp_path):
    scanner = MarketScanner(tmp_path, FilterConfig())
    assert scanner.load_candles(AS_OF) == {}
