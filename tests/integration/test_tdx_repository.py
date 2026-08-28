"""仓储集成测试：临时 .day 文件 → DataFrame（真实走 tdx 解析）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from errors import SymbolNotFoundError
from repositories.daily_bar_repository import TdxDailyBarRepository
from tests.helpers import build_day_bytes, make_daily_records


def test_reads_day_file_into_dataframe(tmp_path):
    market_dir = tmp_path / "sh" / "lday"
    market_dir.mkdir(parents=True)
    (market_dir / "sh600519.day").write_bytes(build_day_bytes(make_daily_records(20)))

    repo = TdxDailyBarRepository(tmp_path)
    df = repo.get_daily_bars("600519")

    assert len(df) == 20
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume", "amount"]
    assert df["close"].iloc[0] == pytest.approx(10.0)
    assert df["date"].is_monotonic_increasing


def test_symbol_not_found_raises(tmp_path):
    repo = TdxDailyBarRepository(tmp_path)
    with pytest.raises(SymbolNotFoundError):
        repo.get_daily_bars("999999")


def test_real_hsjday_600519_if_present():
    """本地有真实 hsjday 数据时的端到端冒烟测试（没有则跳过）。"""
    root = Path.home() / "Desktop" / "每日复盘" / "hsjday"
    if not (root / "sh" / "lday" / "sh600519.day").exists():
        pytest.skip("本地 hsjday 数据不存在，跳过")

    repo = TdxDailyBarRepository(root)
    df = repo.get_daily_bars("600519")

    assert len(df) > 100
    assert df["close"].iloc[-1] > 0
    assert df["date"].is_monotonic_increasing
