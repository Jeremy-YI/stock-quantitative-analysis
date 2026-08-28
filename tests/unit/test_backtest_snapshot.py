"""回测快照测试：固定合成 K 线 + 固定信号 + 固定日期 → 断言报告稳定。

快照由 scripts/make_backtest_snapshot.py 生成并提交；本测试用同一份数据重跑
并逐字节比对，锁死胜率 / 盈亏比 / 衰减等统计口径的回归。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from backtest.config import BacktestConfig
from backtest.engine import BacktestEngine, DictCandlesProvider
from strategies.signal import Signal
from tests.helpers import make_candle_df

SNAPSHOT = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "snapshots"
    / "backtest_verification.json"
)


def _candles() -> dict:
    base = date(2026, 6, 1)
    rising = [10.0 * (1.03**i) for i in range(60)]
    falling = [30.0 * (0.97**i) for i in range(60)]
    choppy = [20.0 + (1.0 if i % 2 == 0 else -1.0) for i in range(60)]
    return {
        "600000": make_candle_df(rising, start=base),
        "300001": make_candle_df(falling, start=base),
        "000002": make_candle_df(choppy, start=base),
    }


def _signals() -> list[Signal]:
    days = [date(2026, 7, d) for d in (6, 13, 20, 27)]
    out: list[Signal] = []
    for d in days:
        out.append(Signal(symbol="600000", strategy="b1b2b3", signal_type="b1", score=1.0, triggered_at=d))
        out.append(Signal(symbol="300001", strategy="pin30", signal_type="b1_w", score=1.0, triggered_at=d))
        out.append(Signal(symbol="000002", strategy="stealth_rally", signal_type="stealth_rally", score=1.0, triggered_at=d))
    return out


def _run() -> dict:
    engine = BacktestEngine(DictCandlesProvider(_candles()), BacktestConfig())
    signals = _signals()
    return {
        "verification": engine.run_verification(signals).model_dump(mode="json"),
        "portfolio": engine.run_portfolio(signals).model_dump(mode="json"),
    }


def test_backtest_snapshot():
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert _run() == expected


def test_backtest_snapshot_is_non_trivial():
    """快照应有信号与统计，保证有防回归价值。"""
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert data["verification"]["total_signals"] > 0
    assert len(data["verification"]["by_strategy"]) > 0
    assert data["portfolio"]["filled_buys"] > 0
