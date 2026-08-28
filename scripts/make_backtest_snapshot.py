#!/usr/bin/env python3
"""生成回测快照 fixture（tests/fixtures/snapshots/backtest_verification.json）。

与 make_strategy_snapshots.py 同理：用固定合成 K 线 + 固定信号 + 固定日期，
跑信号验证 + 组合回测，把完整报告序列化提交。回测统计是纯函数 + 确定性舍入，
快照用于锁死「统计口径」回归（任何胜率/盈亏比/衰减算法的改动都会让快照失配）。

用法（仓库根目录）：

    .venv/bin/python scripts/make_backtest_snapshot.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.config import BacktestConfig
from backtest.engine import BacktestEngine, DictCandlesProvider
from strategies.signal import Signal
from tests.helpers import make_candle_df

SNAPSHOT = (
    ROOT / "tests" / "fixtures" / "snapshots" / "backtest_verification.json"
)


def _candles() -> dict:
    """三只形态不同的合成标的（涨 / 跌 / 震荡）。"""
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
    """固定信号（跨多个交易日，覆盖多策略/多板块）。"""
    days = [date(2026, 7, d) for d in (6, 13, 20, 27)]
    out: list[Signal] = []
    for d in days:
        out.append(Signal(symbol="600000", strategy="b1b2b3", signal_type="b1", score=1.0, triggered_at=d))
        out.append(Signal(symbol="300001", strategy="pin30", signal_type="b1_w", score=1.0, triggered_at=d))
        out.append(Signal(symbol="000002", strategy="stealth_rally", signal_type="stealth_rally", score=1.0, triggered_at=d))
    return out


def main() -> None:
    engine = BacktestEngine(DictCandlesProvider(_candles()), BacktestConfig())
    signals = _signals()

    verification = engine.run_verification(signals)
    portfolio = engine.run_portfolio(signals)

    snapshot = {
        "verification": verification.model_dump(mode="json"),
        "portfolio": portfolio.model_dump(mode="json"),
    }
    SNAPSHOT.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已写入 {SNAPSHOT}")


if __name__ == "__main__":
    main()
