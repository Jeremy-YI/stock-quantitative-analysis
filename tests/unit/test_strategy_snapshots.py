"""快照测试：固定数据切片 + 日期，断言选股结果与 signal 明细稳定。

这是防回归的地基——任何指标公式 / 阈值的改动都会让这里的快照失配。

快照由 scripts/make_strategy_snapshots.py 生成并提交；本测试用同一份数据
重跑 scan 再逐字节比对。ETF 策略用合成 K 线（跌幅 -35% + MACD 底背离）快照。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from strategies import REGISTRY
from tests.helpers import load_market_fixture, make_candle_df, signals_to_json

SNAPSHOTS_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "snapshots"
AS_OF = date(2026, 8, 27)


def _etf_candles() -> dict:
    """与 make_strategy_snapshots.py 完全一致的合成 ETF K 线。"""
    closes = []
    for i in range(40):
        closes.append(100 - i * (30 / 40))
    base = closes[-1]
    for i in range(20):
        closes.append(base - i * 0.3)
    return {"588710": make_candle_df(closes, high_pad=0.01, low_pad=0.01)}


def _snapshot(name: str) -> dict:
    return json.loads((SNAPSHOTS_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _run(name: str) -> dict:
    mod = REGISTRY[name]
    candles = _etf_candles() if name == "etf_accumulation" else load_market_fixture()
    signals = mod.scan(candles, AS_OF)
    return {
        "as_of": AS_OF.isoformat(),
        "strategy": name,
        "signals": signals_to_json(signals),
    }


def test_b1b2b3_snapshot():
    assert _run("b1b2b3") == _snapshot("b1b2b3")


def test_macd_resonance_snapshot():
    assert _run("macd_resonance") == _snapshot("macd_resonance")


def test_pin30_snapshot():
    assert _run("pin30") == _snapshot("pin30")


def test_stealth_rally_snapshot():
    assert _run("stealth_rally") == _snapshot("stealth_rally")


def test_etf_accumulation_snapshot():
    assert _run("etf_accumulation") == _snapshot("etf_accumulation")


def test_snapshots_are_non_empty():
    """除极端情况外，快照应包含信号（保证快照有防回归价值）。"""
    for name in ("b1b2b3", "macd_resonance", "pin30", "stealth_rally", "etf_accumulation"):
        assert len(_snapshot(name)["signals"]) > 0, f"{name} 快照为空"
