#!/usr/bin/env python3
"""扫描新策略 macd_volume_washout + 与其余六策略并排超额对比（阶段 8）。

只扫描 macd_volume_washout（个股宇宙），其余六策略信号复用
``data/signals_cache.pkl``（由 scripts/run_signal_overlay.py 生成）。
合并后跑回测引擎的验证模式，输出七策略 1/3/5/10/20 日超额胜率并排表。

用法（仓库根目录）：

    .venv/bin/python scripts/run_macd_volume_washout.py --start 2026-03-01 --end 2026-08-27 --jobs 8

可选 --cache 把新策略信号缓存到 data/macd_volume_washout_signals.pkl。
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import pickle
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
from strategies import REGISTRY
from strategies.filters import SymbolKind, filter_for_kinds
from strategies.scanner import MarketScanner

HSJDAY = resolve_hsjday_root()
SIGNALS_CACHE = ROOT / "data" / "signals_cache.pkl"
NEW_CACHE = ROOT / "data" / "macd_volume_washout_signals.pkl"
STRATEGY = "macd_volume_washout"


def load_universe(end: date) -> tuple[dict, dict[str, SymbolKind]]:
    scanner = MarketScanner(HSJDAY)
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


_G_CANDLES: dict = {}
_G_SYMBOLS: set[str] = set()


def _init_worker(candles: dict, symbols: set[str]) -> None:
    global _G_CANDLES, _G_SYMBOLS
    _G_CANDLES = candles
    _G_SYMBOLS = symbols


def _scan_one(day: date):
    mod = REGISTRY[STRATEGY]
    sliced = {
        symbol: _G_CANDLES[symbol][_G_CANDLES[symbol]["date"] <= day]
        for symbol in _G_SYMBOLS
        if symbol in _G_CANDLES
    }
    return day, mod.scan(sliced, day)


def scan_new_strategy(candles, symbols, days, jobs, cache_path):
    if cache_path and Path(cache_path).exists():
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    if jobs > 1 and len(days) > 1:
        ctx = multiprocessing.get_context("fork")
        with ctx.Pool(jobs, initializer=_init_worker, initargs=(candles, symbols)) as pool:
            per_day = pool.map(_scan_one, days)
    else:
        _init_worker(candles, symbols)
        per_day = [_scan_one(d) for d in days]

    signals = []
    for _day, sigs in sorted(per_day, key=lambda x: x[0]):
        signals.extend(sigs)

    if cache_path:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "wb") as f:
            pickle.dump(signals, f)
    return signals


def main() -> None:
    parser = argparse.ArgumentParser(description="扫描 macd_volume_washout + 七策略对比")
    parser.add_argument("--start", default="2026-03-01")
    parser.add_argument("--end", default="2026-08-27")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--cache", default=str(NEW_CACHE))
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    t0 = time.time()
    print(f"加载全市场 K 线（个股+ETF，尾段 800 根）...", flush=True)
    candles, kind_map = load_universe(end)
    print(f"  已加载 {len(candles)} 只标的，耗时 {time.time()-t0:.1f}s", flush=True)

    symbols = {s for s in candles if kind_map.get(s) in (SymbolKind.STOCK, SymbolKind.STOCK.value)}
    days = trading_days(start, end)
    print(f"扫描 {STRATEGY}（{len(days)} 个交易日）...", flush=True)

    new_signals = scan_new_strategy(candles, symbols, days, args.jobs, args.cache)
    print(f"新策略信号 {len(new_signals)} 条，耗时 {time.time()-t0:.1f}s", flush=True)

    if not SIGNALS_CACHE.exists():
        print(f"缺少六策略信号缓存 {SIGNALS_CACHE}，请先跑 scripts/run_signal_overlay.py")
        return

    with open(SIGNALS_CACHE, "rb") as f:
        old_signals = pickle.load(f)

    all_signals = old_signals + new_signals
    print(f"合并后总信号 {len(all_signals)} 条（六策略 {len(old_signals)} + 新策略 {len(new_signals)}）", flush=True)

    config = BacktestConfig()
    engine = BacktestEngine(DictCandlesProvider(candles), config, kind_map=kind_map)
    verification = engine.run_verification(all_signals, start=start, end=end)

    print(f"\n{'='*100}")
    print(f"七策略超额胜率并排对比（{start} ~ {end}，pp = 相对同期同宇宙基线）")
    print(f"{'='*100}")
    print(f"  {'策略':<20s}{'选择性':>8s}{'日均信号':>10s}", end="")
    for h in verification.hold_days:
        print(f"{str(h)+'日':>11s}", end="")
    print(f"{'20日超额收益':>12s}")
    for sr in verification.by_strategy:
        sel = f"{sr.selectivity*100:.1f}%" if sr.selectivity is not None else "—"
        spd = f"{sr.signals_per_day:.1f}" if sr.signals_per_day is not None else "—"
        line = f"  {sr.strategy:<20s}{sel:>8s}{spd:>10s}"
        for h in verification.hold_days:
            hold = next((x for x in sr.holds if x.hold_days == h), None)
            if hold and hold.excess_win_rate is not None:
                line += f"{hold.excess_win_rate*100:+10.1f}pp"
            else:
                line += f"{'—':>11s}"
        h20 = next((x for x in sr.holds if x.hold_days == 20), None)
        exr = f"{h20.excess_return*100:+.2f}%" if h20 and h20.excess_return is not None else "—"
        line += f"{exr:>12s}"
        print(line)

    # 市场基线
    print(f"\n同期市场基线：")
    for b in verification.baselines:
        cells = "  ".join(f"{h.hold_days}日 {h.win_rate*100:.1f}%" for h in b.holds)
        print(f"  {b.universe:<6s}（{b.size} 只） {cells}")


if __name__ == "__main__":
    main()
