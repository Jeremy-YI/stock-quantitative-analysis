#!/usr/bin/env python3
"""真实历史回测跑批：五个策略逐日扫描 → 持有 N 日收益 + 衰减 + 组合净值。

用法（仓库根目录）：

    .venv/bin/python scripts/run_backtest.py \
        --start 2026-06-01 --end 2026-08-27

数据源：本地 hsjday（只读）。流程：
    1) 一次性加载个股 + ETF 全量尾段 K 线（tail 800，避免逐日重读文件）；
    2) 按交易日逐日切片，跑五个策略的 scan 收集信号；
    3) 用回测引擎算持有 1/3/5/10/20 日收益、按策略/板块聚合、衰减曲线、组合净值；
    4) 打印 Markdown 风格报告，可选落 JSON（--out）。

性能：单日全市场扫描约 1 分钟（见 docs/策略迁移说明.md），60 个交易日约 40 分钟。
可选 --jobs 用多进程（fork）加速（实测 124 个交易日、--jobs 8 约 33 分钟）。
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
from market.calendar import trading_days
from strategies import REGISTRY
from strategies.filters import SymbolKind, filter_for_kinds
from strategies.scanner import MarketScanner

HSJDAY = Path.home() / "Desktop" / "每日复盘" / "hsjday"


def load_universe(end: date) -> tuple[dict, dict[str, SymbolKind]]:
    """一次性加载个股 + ETF 尾段 K 线，返回 (candles, {symbol: 种类})。"""
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


# ---- 多进程（fork）共享只读 candles ----
_G_CANDLES: dict = {}
_G_SYMBOLS: dict[str, set[str]] = {}


def _init_worker(candles: dict, symbols_by_strategy: dict[str, set[str]]) -> None:
    global _G_CANDLES, _G_SYMBOLS
    _G_CANDLES = candles
    _G_SYMBOLS = symbols_by_strategy


def _scan_one(day: date):
    """worker 入口：读全局共享 candles，扫一个交易日。"""
    return day, scan_day(_G_CANDLES, _G_SYMBOLS, day)


def main() -> None:
    parser = argparse.ArgumentParser(description="真实历史回测跑批")
    parser.add_argument("--start", required=True, help="回测起始日 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="回测结束日 YYYY-MM-DD")
    parser.add_argument("--out", default=None, help="可选：报告 JSON 输出路径")
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

    # 各策略目标宇宙的 symbol 集合（按 TARGET_KINDS 过滤，数据不足由策略内部跳过）
    symbols_by_strategy: dict[str, set[str]] = {}
    for strategy, mod in REGISTRY.items():
        allowed = set(mod.TARGET_KINDS)
        symbols_by_strategy[strategy] = {
            s for s in candles if kind_map.get(s) in allowed
        }

    days = trading_days(start, end)
    print(f"交易日区间 {start} ~ {end}，共 {len(days)} 个交易日，逐日扫描...", flush=True)

    if args.jobs > 1 and len(days) > 1:
        ctx = multiprocessing.get_context("fork")
        with ctx.Pool(
            args.jobs, initializer=_init_worker, initargs=(candles, symbols_by_strategy)
        ) as pool:
            per_day = pool.map(_scan_one, days)
    else:
        # 串行路径也要先初始化全局 candles，否则 _scan_one 读到空 dict（0 信号）
        _init_worker(candles, symbols_by_strategy)
        per_day = [_scan_one(d) for d in days]

    all_signals = []
    for day, signals in sorted(per_day, key=lambda x: x[0]):
        all_signals.extend(signals)
    print(f"\n扫描完成，总信号 {len(all_signals)}，累计耗时 {time.time()-t0:.1f}s", flush=True)

    # 回测引擎（传入 kind_map 供基线分宇宙计算，start/end 对齐基线区间）
    config = BacktestConfig()
    engine = BacktestEngine(DictCandlesProvider(candles), config, kind_map=kind_map)
    verification = engine.run_verification(all_signals, start=start, end=end)
    portfolio = engine.run_portfolio(all_signals)

    _print_report(verification, portfolio, start, end, all_signals)

    if args.out:
        payload = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "total_signals": len(all_signals),
            "verification": verification.model_dump(mode="json"),
            "portfolio": portfolio.model_dump(mode="json"),
        }
        Path(args.out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"报告已写入 {args.out}")


def _print_report(verification, portfolio, start, end, signals) -> None:
    """打印 Markdown 风格报告（emoji + 中文 + 对齐）。"""
    print(f"\n{'='*72}")
    print(f"【📊 回测报告】{start} ~ {end}")
    print(f"  总信号 {len(signals)} 条，持有期 {verification.hold_days}")

    # 基线（按宇宙种类）
    if verification.baselines:
        print(f"\n--- 同期市场基线（正收益比例 / 平均收益） ---")
        for b in verification.baselines:
            row = f"  {b.universe:<8s}（标的 {b.size}）"
            for h in b.holds:
                row += f"  {h.hold_days}日 {h.win_rate*100:.1f}%/{h.avg_return*100:+.2f}%"
            print(row)

    print(f"\n--- 按策略 · 胜率 / 平均收益 / 超额（%） ---")
    print(
        f"  {'策略':<16s}{'持有':>4s}{'样本':>8s}{'胜率':>7s}{'基线':>7s}"
        f"{'超额胜':>7s}{'平均':>8s}{'超额收益':>9s}"
    )
    for sr in verification.by_strategy:
        for h in sr.holds:
            base = f"{h.baseline_win_rate*100:.1f}%" if h.baseline_win_rate is not None else "—"
            exw = f"{h.excess_win_rate*100:+.1f}pp" if h.excess_win_rate is not None else "—"
            exr = f"{h.excess_return*100:+.2f}%" if h.excess_return is not None else "—"
            print(
                f"  {sr.strategy:<16s}{h.hold_days:>4d}{h.n:>8d}"
                f"{h.win_rate*100:>6.1f}%{base:>7s}{exw:>7s}"
                f"{h.avg_return*100:>7.2f}%{exr:>9s}"
            )

    print(f"\n--- 选择性（日均信号数 / 宇宙标的数） ---")
    for sr in verification.by_strategy:
        sel = f"{sr.selectivity*100:.1f}%" if sr.selectivity is not None else "—"
        spd = f"{sr.signals_per_day:.1f}" if sr.signals_per_day is not None else "—"
        print(
            f"  {sr.strategy:<16s} 日均 {spd} 条 / 宇宙 {sr.universe_size or '—'} 只"
            f" = 选择性 {sel}"
        )

    print(f"\n--- 组合回测 ---")
    print(f"  总收益 {portfolio.total_return*100:+.2f}%  最大回撤 {portfolio.max_drawdown*100:.2f}%  "
          f"夏普 {portfolio.sharpe if portfolio.sharpe is not None else '—'}")
    print(f"  成交 {portfolio.trade_count} 笔，建仓 {portfolio.filled_buys}，跳过 {portfolio.skipped_buys}")

    print(f"\n--- 策略衰减（滚动 20 日胜率，末点） ---")
    for s in verification.decay:
        if s.window == 20 and s.points:
            last = s.points[-1]
            exw = f"{last.excess_win_rate*100:+.1f}pp" if last.excess_win_rate is not None else "—"
            print(
                f"  {s.strategy:<16s} 末点胜率 {last.win_rate*100:.1f}%"
                f"  (n={last.n}, {last.date})  超额 {exw}"
            )


if __name__ == "__main__":
    main()
