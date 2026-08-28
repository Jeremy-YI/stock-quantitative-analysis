#!/usr/bin/env python3
"""样本外（OOS）策略超额验证：七个策略在样本内 + 三段样本外区间的 20 日超额对照。

核心问题（阶段 9 最高优先级）：阶段 8 的「七策略超额排序」全部来自 2026-03~08
单区间（样本内）。本脚本把七个策略（含 macd_volume_washout）在三段 OOS 区间重跑，
输出每段 20 日超额胜率 / 超额收益 / 选择性 / 日均信号数 / 样本量，并排对照，
判定每个策略是稳健 / 过拟合 / 环境依赖。

区间：
    IS     2026-03-01 ~ 2026-08-27   （样本内，读 data/signals_cache.pkl + washout 缓存）
    OOS-A  2023-01-01 ~ 2023-12-31
    OOS-B  2024-01-01 ~ 2024-12-31
    OOS-C  2025-01-01 ~ 2026-02-28

用法（仓库根目录）：
    .venv/bin/python scripts/run_oos_strategies.py --windows A B C --jobs 10 \
        --out data/oos_strategies.json

性能：OOS 窗口约 240~270 交易日，--jobs 10（12 核）每窗口约 1 小时，
建议后台跑（exec background + process poll）。IS 窗口读缓存，秒级。
"""

from __future__ import annotations

import argparse
import json
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
WASHOUT_CACHE = ROOT / "data" / "macd_volume_washout_signals.pkl"

WINDOWS: dict[str, tuple[str, str]] = {
    "IS": ("2026-03-01", "2026-08-27"),
    "A": ("2023-01-01", "2023-12-31"),
    "B": ("2024-01-01", "2024-12-31"),
    "C": ("2025-01-01", "2026-02-28"),
}
WINDOW_LABELS = {"IS": "IS", "A": "OOS-A", "B": "OOS-B", "C": "OOS-C"}


def load_universe(end: date, lookback: int = 800) -> tuple[dict, dict[str, SymbolKind]]:
    """一次性加载个股 + ETF 尾段 K 线（与 run_backtest.load_universe 一致）。

    关键修正（阶段 9）：通达信 .day 文件最新到数据末日（2026-08），而 OOS 窗口
    结束日更早。``MarketScanner._read_day_tail`` 读的是「文件尾部 lookback 根」
    （末尾=数据末日），若不处理，OOS 窗口早段会被截断成空/短历史。这里多读
    ``_EXTRA_TAIL`` 根，再切到 ``date <= end`` 后取尾部 ``lookback`` 根，
    保证每个窗口都拿到「截止 end 的完整回看」。

    lookback 控制每只标的保留多少根：默认 800（覆盖 macd_resonance 需 30 月线）；
    若排除 macd_resonance，其余六策略最多只回看 250 根，可用 300 大幅降内存。
    """
    _EXTRA_TAIL = 1000  # 覆盖 OOS 最早窗口（2023-01）到数据末日（2026-08）的bar数
    scanner = MarketScanner(HSJDAY, lookback=lookback + _EXTRA_TAIL)
    candles: dict = {}
    kind_map: dict[str, SymbolKind] = {}
    for kind, kinds in (
        (SymbolKind.STOCK, (SymbolKind.STOCK,)),
        (SymbolKind.ETF, (SymbolKind.ETF,)),
    ):
        loaded = scanner.load_candles(end, filter_config=filter_for_kinds(kinds))
        for symbol, df in loaded.items():
            if df is None or df.empty:
                continue
            df = df[df["date"] <= end]
            if len(df) > lookback:
                df = df.tail(lookback).reset_index(drop=True)
            if df.empty:
                continue
            candles.setdefault(symbol, df)
            kind_map[symbol] = kind
    return candles, kind_map


def scan_day(candles: dict, symbols_by_strategy: dict[str, set[str]], day: date):
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


def load_is_signals() -> list:
    """IS 窗口信号：合并六策略缓存 + washout 缓存（避免重扫 124 天）。"""
    signals = list(pickle.load(open(SIGNALS_CACHE, "rb")))
    if WASHOUT_CACHE.exists():
        signals.extend(pickle.load(open(WASHOUT_CACHE, "rb")))
    return signals


def scan_window(window: str, jobs: int, lookback: int = 800, exclude: set[str] | None = None) -> list:
    start, end = (date.fromisoformat(x) for x in WINDOWS[window])
    t0 = time.time()
    print("  加载全市场 K 线（尾段 %d）..." % lookback, flush=True)
    candles, kind_map = load_universe(end, lookback)
    print("  已加载 %d 只，耗时 %.1fs" % (len(candles), time.time() - t0), flush=True)

    symbols_by_strategy: dict[str, set[str]] = {}
    for strategy, mod in REGISTRY.items():
        if exclude and strategy in exclude:
            continue
        allowed = set(mod.TARGET_KINDS)
        symbols_by_strategy[strategy] = {
            s for s in candles if kind_map.get(s) in allowed
        }

    days = trading_days(start, end)
    print("  交易日 %d 个，逐日扫描（jobs=%d）..." % (len(days), jobs), flush=True)

    if jobs > 1 and len(days) > 1:
        ctx = multiprocessing.get_context("fork")
        with ctx.Pool(jobs, initializer=_init_worker, initargs=(candles, symbols_by_strategy)) as pool:
            # imap（惰性）逐日取回，避免 map 先把全部结果缓存进内存（父进程内存峰值减半）
            per_day = pool.imap(_scan_one, days, chunksize=1)
            all_signals = []
            for _day, sigs in per_day:
                all_signals.extend(sigs)
    else:
        _init_worker(candles, symbols_by_strategy)
        all_signals = []
        for d in days:
            all_signals.extend(_scan_one(d)[1])
    print("  扫描完成，总信号 %d，耗时 %.1fs" % (len(all_signals), time.time() - t0), flush=True)
    return all_signals


def summarize(signals: list, candles: dict, kind_map: dict, start: date, end: date) -> dict:
    """用回测引擎算 20 日超额等关键指标，返回可 JSON 化的摘要。"""
    config = BacktestConfig()
    engine = BacktestEngine(DictCandlesProvider(candles), config, kind_map=kind_map)
    verification = engine.run_verification(signals, start=start, end=end)

    headline = config.hold_days[-1]  # 20 日
    out: dict = {"baselines": {}, "strategies": {}}
    for b in verification.baselines:
        holds = {h.hold_days: {"win_rate": h.win_rate, "avg_return": h.avg_return} for h in b.holds}
        out["baselines"][b.universe] = {"size": b.size, "holds": holds}
    for sr in verification.by_strategy:
        h = next((x for x in sr.holds if x.hold_days == headline), None)
        if h is None:
            continue
        out["strategies"][sr.strategy] = {
            "universe": sr.universe,
            "signals_per_day": sr.signals_per_day,
            "selectivity": sr.selectivity,
            "n": h.n,
            "win_rate": h.win_rate,
            "avg_return": h.avg_return,
            "baseline_win_rate": h.baseline_win_rate,
            "excess_win_rate": h.excess_win_rate,
            "excess_return": h.excess_return,
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="OOS 策略超额验证")
    parser.add_argument("--windows", nargs="+", default=["IS", "A", "B", "C"],
                        help="要跑的窗口（IS/A/B/C），默认全跑")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--lookback", type=int, default=800,
                        help="单只标的回看根数（默认 800；排除 macd_resonance 后可用 300 降内存）")
    parser.add_argument("--exclude", nargs="*", default=[],
                        help="要排除的策略名（如 macd_resonance）")
    parser.add_argument("--out", default="data/oos_strategies.json")
    args = parser.parse_args()

    exclude = set(args.exclude)
    results: dict = {}
    for window in args.windows:
        label = WINDOW_LABELS[window]
        start, end = (date.fromisoformat(x) for x in WINDOWS[window])
        print("\n" + "=" * 80)
        print("【%s】%s ~ %s" % (label, start, end), flush=True)

        if window == "IS":
            signals = load_is_signals()
            if exclude:
                signals = [s for s in signals if s.strategy not in exclude]
            print("  读缓存信号 %d 条" % len(signals), flush=True)
            candles, kind_map = load_universe(end, args.lookback)
        else:
            cache_path = ROOT / "data" / ("oos_signals_%s.pkl" % label.lower())
            if cache_path.exists():
                signals = pickle.load(open(cache_path, "rb"))
                if exclude:
                    signals = [s for s in signals if s.strategy not in exclude]
                print("  读缓存信号 %d 条（%s）" % (len(signals), cache_path.name), flush=True)
            else:
                signals = scan_window(window, args.jobs, lookback=args.lookback, exclude=exclude)
                cache_path.write_bytes(pickle.dumps(signals))
                print("  信号缓存写入 %s" % cache_path.name, flush=True)
            candles, kind_map = load_universe(end, args.lookback)

        summary = summarize(signals, candles, kind_map, start, end)
        results[label] = summary

    # 打印对照表
    _print_comparison(results)

    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n结构化快照已写入 %s" % args.out)


def _print_comparison(results: dict) -> None:
    strat_names: list[str] = []
    for label, r in results.items():
        for s in r.get("strategies", {}):
            if s not in strat_names:
                strat_names.append(s)
    strat_names.sort()

    labels = list(results.keys())
    print("\n" + "=" * 100)
    print("七策略 20 日超额对照（样本内 vs 三段样本外）")
    print("=" * 100)
    header = "  %-20s" % "策略"
    for l in labels:
        header += "%16s" % l
    print(header)
    # 主表：每策略每窗口的 20 日超额胜率（pp）
    print("  20 日超额胜率（pp）：")
    hdr = "    %-20s" % "策略"
    for l in labels:
        hdr += "%10s" % l
    print(hdr)
    for s in strat_names:
        row = "    %-20s" % s
        for l in labels:
            sr = results.get(l, {}).get("strategies", {}).get(s)
            v = sr["excess_win_rate"] * 100 if sr and sr.get("excess_win_rate") is not None else None
            row += "%10s" % ("—" if v is None else "%+.1f" % v)
        print(row)

    print("\n  20 日超额收益（%）：")
    hdr = "    %-20s" % "策略"
    for l in labels:
        hdr += "%10s" % l
    print(hdr)
    for s in strat_names:
        row = "    %-20s" % s
        for l in labels:
            sr = results.get(l, {}).get("strategies", {}).get(s)
            v = sr["excess_return"] * 100 if sr and sr.get("excess_return") is not None else None
            row += "%10s" % ("—" if v is None else "%+.2f" % v)
        print(row)

    print("\n  选择性（% 宇宙）：")
    hdr = "    %-20s" % "策略"
    for l in labels:
        hdr += "%10s" % l
    print(hdr)
    for s in strat_names:
        row = "    %-20s" % s
        for l in labels:
            sr = results.get(l, {}).get("strategies", {}).get(s)
            v = sr["selectivity"] * 100 if sr and sr.get("selectivity") is not None else None
            row += "%10s" % ("—" if v is None else "%.1f" % v)
        print(row)

    print("\n  日均信号数：")
    hdr = "    %-20s" % "策略"
    for l in labels:
        hdr += "%10s" % l
    print(hdr)
    for s in strat_names:
        row = "    %-20s" % s
        for l in labels:
            sr = results.get(l, {}).get("strategies", {}).get(s)
            v = sr["signals_per_day"] if sr else None
            row += "%10s" % ("—" if v is None else "%.1f" % v)
        print(row)

    print("\n  样本量（20 日收益有效数）：")
    hdr = "    %-20s" % "策略"
    for l in labels:
        hdr += "%10s" % l
    print(hdr)
    for s in strat_names:
        row = "    %-20s" % s
        for l in labels:
            sr = results.get(l, {}).get("strategies", {}).get(s)
            v = sr["n"] if sr else None
            row += "%10s" % ("—" if v is None else "%d" % v)
        print(row)


if __name__ == "__main__":
    main()
