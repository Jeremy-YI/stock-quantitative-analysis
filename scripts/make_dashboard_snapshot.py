#!/usr/bin/env python3
"""生成概览页快照（data/dashboard_snapshot.json），供 Dashboard 首页展示。

数据源：本地通达信 hsjday（只读），默认区间与阶段 4.5 回测一致
（2026-03-01 ~ 2026-08-27，124 个交易日，见 docs/回测迁移说明.md）。

流程（与 scripts/run_backtest.py 同源）：
    1) 一次性加载个股 + ETF 尾段 K 线；
    2) 按交易日逐日跑五个策略 scan 收集信号；
    3) 回测引擎算持有 1/3/5/10/20 日收益、按策略聚合、算基线；
    4) 抽出概览页需要的字段（各策略当日信号数/选择性/超额胜率 + 市场基线），
       写成 data/dashboard_snapshot.json。

性能：单日全市场扫描约 1 分钟，124 个交易日约 30 分钟（--jobs 8 并行）。
API 概览页只读这个快照，不在每次加载时实时扫描。

用法（仓库根目录）：

    .venv/bin/python scripts/make_dashboard_snapshot.py            # 全量（约 30 分钟）
    .venv/bin/python scripts/make_dashboard_snapshot.py --jobs 8
    .venv/bin/python scripts/make_dashboard_snapshot.py --start 2026-07-01 --end 2026-08-27
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.config import BacktestConfig
from backtest.engine import BacktestEngine, DictCandlesProvider
from datasource.tdx import resolve_hsjday_root
from market.calendar import trading_days
from market.regime import compute_market_series, snapshot_at
from strategies import REGISTRY
from strategies.filters import SymbolKind, filter_for_kinds
from strategies.scanner import MarketScanner

# 概览页超额胜率的持有期（与 docs/回测迁移说明.md 的 20 日口径一致）
HEADLINE_HOLD_DAYS = 20

DEFAULT_START = date(2026, 3, 1)
DEFAULT_END = date(2026, 8, 27)


def load_universe(end: date) -> tuple[dict, dict[str, SymbolKind]]:
    """一次性加载个股 + ETF 尾段 K 线，返回 (candles, {symbol: 种类})。"""
    scanner = MarketScanner(resolve_hsjday_root())
    candles: dict = {}
    kind_map: dict[str, SymbolKind] = {}
    for kind, kinds in (
        (SymbolKind.STOCK, (SymbolKind.STOCK,)),
        (SymbolKind.ETF, (SymbolKind.ETF,)),
    ):
        loaded = scanner.load_candles(end, filter_config=filter_for_kinds(kinds))
        for symbol, df in loaded.items():
            candles.setdefault(symbol, df)
            kind_map[symbol] = kind
    return candles, kind_map


def scan_day(candles: dict, symbols_by_strategy: dict[str, set[str]], day: date):
    """对某个交易日跑全部策略，返回当日信号列表。"""
    signals = []
    for strategy, symbols in symbols_by_strategy.items():
        mod = REGISTRY[strategy]
        sliced = {
            symbol: candles[symbol][candles[symbol]["date"] <= day]
            for symbol in symbols
            if symbol in candles
        }
        signals.extend(mod.scan(sliced, day))
    return signals


_G_CANDLES: dict = {}
_G_SYMBOLS: dict[str, set[str]] = {}


def _init_worker(candles: dict, symbols_by_strategy: dict[str, set[str]]) -> None:
    global _G_CANDLES, _G_SYMBOLS
    _G_CANDLES = candles
    _G_SYMBOLS = symbols_by_strategy


def _scan_one(day: date):
    return day, scan_day(_G_CANDLES, _G_SYMBOLS, day)


def build_snapshot(
    start: date,
    end: date,
    jobs: int,
    candles: dict,
    kind_map: dict[str, SymbolKind],
    symbols_by_strategy: dict[str, set[str]],
) -> dict:
    """跑回测，抽出概览页字段，返回快照 dict。"""
    days = trading_days(start, end)

    if jobs > 1 and len(days) > 1:
        ctx = multiprocessing.get_context("fork")
        with ctx.Pool(
            jobs, initializer=_init_worker, initargs=(candles, symbols_by_strategy)
        ) as pool:
            per_day = pool.map(_scan_one, days)
    else:
        _init_worker(candles, symbols_by_strategy)
        per_day = [_scan_one(d) for d in days]

    all_signals = []
    for _day, signals in sorted(per_day, key=lambda x: x[0]):
        all_signals.extend(signals)

    config = BacktestConfig()
    engine = BacktestEngine(DictCandlesProvider(candles), config, kind_map=kind_map)
    verification = engine.run_verification(all_signals, start=start, end=end)

    as_of = end
    # 当日信号数：按策略数 triggered_at == as_of 的信号
    signals_today: dict[str, int] = {name: 0 for name in REGISTRY}
    for s in all_signals:
        if s.triggered_at == as_of and s.strategy in signals_today:
            signals_today[s.strategy] += 1

    by_strategy = {sr.strategy: sr for sr in verification.by_strategy}

    strategies = []
    for name, mod in REGISTRY.items():
        sr = by_strategy.get(name)
        selectivity = sr.selectivity if sr else None
        excess = None
        hold_days = HEADLINE_HOLD_DAYS
        if sr and sr.holds:
            hold = next(
                (h for h in sr.holds if h.hold_days == HEADLINE_HOLD_DAYS),
                sr.holds[0],
            )
            excess = hold.excess_win_rate
            hold_days = hold.hold_days
        strategies.append(
            {
                "name": name,
                "description": mod.DESCRIPTION,
                "signals_today": signals_today.get(name, 0),
                "selectivity": selectivity,
                "excess_win_rate": excess,
                "hold_days": hold_days,
            }
        )

    baselines = []
    for b in verification.baselines:
        baselines.append(
            {
                "universe": b.universe,
                "size": b.size,
                "holds": [
                    {"hold_days": h.hold_days, "win_rate": h.win_rate, "avg_return": h.avg_return}
                    for h in b.holds
                ],
            }
        )

    # 当前市场环境（regime）：个股宇宙等权指数，末日快照
    regime = None
    stock_candles = {
        sym: df for sym, df in candles.items()
        if kind_map.get(sym) in (SymbolKind.STOCK, SymbolKind.STOCK.value)
    }
    series = compute_market_series(stock_candles)
    snap = snapshot_at(series, end) if not series.empty else None
    if snap is not None:
        from backtest.config import RegimeFilterConfig

        f = RegimeFilterConfig()
        regime = {
            "as_of": end.isoformat(),
            "index_20d_return": round(snap.index_20d_return, 6),
            "activity": round(snap.activity, 6),
            "drawdown": round(snap.drawdown, 6),
            "index_20d_label": snap.labels["index_20d"],
            "activity_label": snap.labels["activity"],
            "drawdown_label": snap.labels["drawdown"],
            "allow_open": f.allow(snap.index_20d_return, snap.activity, snap.drawdown),
        }

    return {
        "as_of": as_of.isoformat(),
        "strategies": strategies,
        "baselines": baselines,
        "regime": regime,
        "last_scan": {
            "status": "ok",
            "as_of": as_of.isoformat(),
            "symbols_scanned": len(candles),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成概览页快照")
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--end", default=DEFAULT_END.isoformat())
    parser.add_argument(
        "--out",
        default=str(ROOT / "data" / "dashboard_snapshot.json"),
        help="输出 JSON 路径",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=os.cpu_count() or 4,
        help="并行进程数（fork 共享只读 candles），1 = 串行",
    )
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    t0 = time.time()
    print(f"加载全市场 K 线（个股+ETF，尾段 800 根）...", flush=True)
    candles, kind_map = load_universe(end)
    print(f"  已加载 {len(candles)} 只标的，耗时 {time.time()-t0:.1f}s", flush=True)

    symbols_by_strategy: dict[str, set[str]] = {}
    for strategy, mod in REGISTRY.items():
        allowed = set(mod.TARGET_KINDS)
        symbols_by_strategy[strategy] = {
            s for s in candles if kind_map.get(s) in allowed
        }

    days = trading_days(start, end)
    print(f"交易日区间 {start} ~ {end}，共 {len(days)} 个交易日，逐日扫描...", flush=True)

    snapshot = build_snapshot(
        start, end, args.jobs, candles, kind_map, symbols_by_strategy
    )
    snapshot["last_scan"]["duration_seconds"] = round(time.time() - t0, 1)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 简要打印关键数字，方便核对
    print(f"\n概览页快照已写入 {out}（as_of={snapshot['as_of']}）")
    for s in snapshot["strategies"]:
        exw = f"{s['excess_win_rate']*100:+.1f}pp" if s["excess_win_rate"] is not None else "—"
        sel = f"{s['selectivity']*100:.1f}%" if s["selectivity"] is not None else "—"
        print(
            f"  {s['name']:<16s} 当日信号 {s['signals_today']:>6d}  选择性 {sel:>6s}"
            f"  {s['hold_days']}日超额胜率 {exw}"
        )
    for b in snapshot["baselines"]:
        cells = "  ".join(f"{h['hold_days']}日 {h['win_rate']*100:.1f}%" for h in b["holds"])
        print(f"  基线 {b['universe']:<6s}（{b['size']} 只） {cells}")


if __name__ == "__main__":
    main()
