"""生成策略快照 fixture（防回归基准）。

读取全市场抽样 fixture（tests/fixtures/market_daily.csv），在固定 as_of 日期跑
各策略 scan，把结果序列化成 JSON 存到 tests/fixtures/snapshots/<strategy>.json。
快照测试（tests/unit/test_strategy_snapshots.py）用同一份数据重跑并逐字节比对，
任何指标公式 / 阈值改动都会让快照失配，从而锁死回归。

ETF 策略用脚本内合成的一段「跌幅 25%-40% + MACD 底背离」K 线生成快照。

运行（仓库根目录）：
    .venv/bin/python scripts/make_strategy_snapshots.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from strategies import REGISTRY
from tests.helpers import load_market_fixture, make_candle_df, signals_to_json

SNAPSHOTS_DIR = ROOT / "tests" / "fixtures" / "snapshots"

AS_OF = date(2026, 8, 27)


def _etf_candles() -> dict:
    """合成一段触发 ETF 吸筹信号的 K 线（跌幅 -35% + MACD 底背离）。"""
    closes = []
    for i in range(40):  # 前 40 日匀速下跌 100 → 70
        closes.append(100 - i * (30 / 40))
    base = closes[-1]
    for i in range(20):  # 后 20 日磨底创新低，跌速递减 → MACD DIF 回升
        closes.append(base - i * 0.3)
    df = make_candle_df(closes, high_pad=0.01, low_pad=0.01)
    return {"588710": df}


def main() -> None:
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    market = load_market_fixture()

    for name, mod in REGISTRY.items():
        if name == "etf_accumulation":
            candles = _etf_candles()
        else:
            candles = market
        signals = mod.scan(candles, AS_OF)
        payload = {"as_of": AS_OF.isoformat(), "strategy": name, "signals": signals_to_json(signals)}
        out = SNAPSHOTS_DIR / f"{name}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ {out.name}: {len(signals)} signals")


if __name__ == "__main__":
    main()
