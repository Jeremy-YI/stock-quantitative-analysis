#!/usr/bin/env python3
"""信号叠加分析 + 加权组合回测（阶段 7 核心产出）。

与 scripts/run_backtest.py 同源，额外做三件事：

    1) 按策略算超额胜率（double_bottom 加入后的六策略并排对比）；
    2) 两两策略「同时触发」的标的叠加分析：算叠加标的的超额胜率，找出最强组合；
    3) 组合回测：等权 vs 按实测超额胜率推导的加权，对比总收益/最大回撤/夏普。

用法（仓库根目录）：

    .venv/bin/python scripts/run_signal_overlay.py --start 2026-03-01 --end 2026-08-27 --jobs 8

可选 --cache 把逐日扫描的 73 万+ 信号缓存到 pickle，二次运行跳过扫描（约 30 分钟）。
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import pickle
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.baseline import compute_baseline
from backtest.config import BacktestConfig
from backtest.engine import BacktestEngine, DictCandlesProvider
from backtest.forward import forward_returns
from datasource.tdx import resolve_hsjday_root
from market.calendar import trading_days
from strategies import REGISTRY
from strategies.filters import SymbolKind, filter_for_kinds
from strategies.scanner import MarketScanner

HSJDAY = resolve_hsjday_root()

# 叠加矩阵 / 权重推导用的持有期（与 docs/回测迁移说明.md 的 20 日口径一致）
HEADLINE_HOLD = 20


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


def _init_worker(candles, symbols_by_strategy):
    global _G_CANDLES, _G_SYMBOLS
    _G_CANDLES = candles
    _G_SYMBOLS = symbols_by_strategy


def _scan_one(day):
    return day, scan_day(_G_CANDLES, _G_SYMBOLS, day)


def collect_signals(candles, symbols_by_strategy, days, jobs, cache_path):
    """逐日扫描收集信号（有缓存则直接读缓存）。"""
    if cache_path and Path(cache_path).exists():
        with open(cache_path, "rb") as f:
            signals = pickle.load(f)
        print(f"缓存命中 {cache_path}：{len(signals)} 条信号，跳过扫描", flush=True)
        return signals

    if jobs > 1 and len(days) > 1:
        ctx = multiprocessing.get_context("fork")
        with ctx.Pool(jobs, initializer=_init_worker, initargs=(candles, symbols_by_strategy)) as pool:
            per_day = pool.map(_scan_one, days)
    else:
        _init_worker(candles, symbols_by_strategy)
        per_day = [_scan_one(d) for d in days]

    signals = []
    for _day, sigs in sorted(per_day, key=lambda x: x[0]):
        signals.extend(sigs)

    if cache_path:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "wb") as f:
            pickle.dump(signals, f)
    return signals


def _universe_baselines(candles, kind_map, start, end, hold_days):
    """按宇宙种类算基线胜率（供叠加矩阵的超额计算）。"""
    groups: dict[str, set[str]] = defaultdict(set)
    for symbol, kind in kind_map.items():
        groups[kind.value].add(symbol)
    out = {}
    for universe, symbols in groups.items():
        stats = compute_baseline(candles, symbols, universe, start, end, hold_days)
        out[universe] = {h.hold_days: h.win_rate for h in stats.holds}
    return out


def overlay_matrix(signals, candles, kind_map, start, end, hold_days):
    """两两策略「同标的同日触发」的叠加超额矩阵。"""
    # strategy -> {(symbol, date)}
    trigger: dict[str, set[tuple[str, date]]] = defaultdict(set)
    for s in signals:
        trigger[s.strategy].add((s.symbol, s.triggered_at))

    names = sorted(REGISTRY.keys())
    baselines = _universe_baselines(candles, kind_map, start, end, hold_days)

    # 预取每标的日线（避免重复 dict 查找）
    def fr(symbol: str, d: date):
        df = candles.get(symbol)
        if df is None or df.empty:
            return None
        return forward_returns(df, d, hold_days)

    matrix: dict[tuple[str, str], dict] = {}
    for a in names:
        for b in names:
            if (a, b) in matrix:
                continue
            co = trigger[a] & trigger[b] if a != b else trigger[a]
            universe = kind_map.get(next(iter(co), ())[0], SymbolKind.STOCK).value if co else "stock"
            base_win = baselines.get(universe, {}).get(HEADLINE_HOLD)
            returns = []
            for symbol, d in co:
                r = fr(symbol, d)
                if r is not None and r.get(HEADLINE_HOLD) is not None:
                    returns.append(r[HEADLINE_HOLD])
            win_rate = sum(1 for r in returns if r > 0) / len(returns) if returns else 0.0
            excess = (win_rate - base_win) if (base_win is not None and returns) else None
            matrix[(a, b)] = {
                "n": len(returns),
                "win_rate": round(win_rate, 4),
                "excess_win_rate": round(excess, 4) if excess is not None else None,
            }
    return matrix, names


def derive_weights(verification, hold_days: int = HEADLINE_HOLD) -> dict[str, float]:
    """按实测超额胜率推导策略权重：weight = max(0, excess_win_rate_20d)，单位 pp。

    负超额 → 权重 0（不建仓）；正超额按比例分配，最高者拿满单只仓位上限。
    """
    weights = {}
    for sr in verification.by_strategy:
        hold = next((h for h in sr.holds if h.hold_days == hold_days), None)
        excess = hold.excess_win_rate if hold else None
        weights[sr.strategy] = max(0.0, excess) if excess is not None else 0.0
    return weights


def _print_strategy_table(verification):
    print(f"\n{'='*100}")
    print(f"【1】六策略超额胜率并排对比（持有 1/3/5/10/20 日，pp = 相对同期同宇宙基线）")
    print(f"{'='*100}")
    print(f"  {'策略':<16s}{'选择性':>8s}{'日均信号':>10s}", end="")
    for h in verification.hold_days:
        print(f"{str(h)+'日':>14s}", end="")
    print()
    for sr in verification.by_strategy:
        sel = f"{sr.selectivity*100:.1f}%" if sr.selectivity is not None else "—"
        spd = f"{sr.signals_per_day:.1f}" if sr.signals_per_day is not None else "—"
        line = f"  {sr.strategy:<16s}{sel:>8s}{spd:>10s}"
        for h in verification.hold_days:
            hold = next((x for x in sr.holds if x.hold_days == h), None)
            if hold and hold.excess_win_rate is not None:
                line += f"{hold.excess_win_rate*100:+10.1f}pp"
            else:
                line += f"{'—':>14s}"
        print(line)


def _print_overlay(matrix, names):
    print(f"\n{'='*100}")
    print(f"【2】两两策略叠加超额矩阵（同时触发标的，持有 {HEADLINE_HOLD} 日超额胜率）")
    print(f"{'='*100}")
    header = "  " + "".join(f"{n:>18s}" for n in names)
    print(header)
    for a in names:
        row = f"  {a:<16s}"
        for b in names:
            key = (a, b) if (a, b) in matrix else (b, a)
            cell = matrix.get(key)
            if cell is None or cell["n"] == 0:
                row += f"{'—':>18s}"
            else:
                ex = cell["excess_win_rate"]
                exs = f"{ex*100:+.1f}pp" if ex is not None else "—"
                row += f"{exs:>18s}"
        print(row)
    print(f"\n  （对角 = 单策略自身；n = 叠加标的-日样本数）")
    for a in names:
        for b in names:
            key = (a, b) if (a, b) in matrix else (b, a)
            cell = matrix.get(key)
            if cell and cell["n"] > 0 and a < b:
                ex = cell["excess_win_rate"]
                exs = f"{ex*100:+.1f}pp" if ex is not None else "—"
                print(f"    {a:<16s}×{b:<16s} n={cell['n']:>8d}  超额 {exs}")


def _print_portfolio(title, report):
    sharpe = f"{report.sharpe:.3f}" if report.sharpe is not None else "—"
    print(f"    {title:<12s} 总收益 {report.total_return*100:+.2f}%  "
          f"最大回撤 {report.max_drawdown*100:.2f}%  夏普 {sharpe}  "
          f"建仓 {report.filled_buys} 成交 {report.trade_count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="信号叠加分析 + 加权组合回测")
    parser.add_argument("--start", default="2026-03-01")
    parser.add_argument("--end", default="2026-08-27")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--out", default=None, help="可选：结果 JSON 输出路径")
    parser.add_argument("--cache", default=str(ROOT / "data" / "signals_cache.pkl"))
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
    signals = collect_signals(candles, symbols_by_strategy, days, args.jobs, args.cache)
    print(f"总信号 {len(signals)}，累计耗时 {time.time()-t0:.1f}s", flush=True)

    config = BacktestConfig()
    engine = BacktestEngine(DictCandlesProvider(candles), config, kind_map=kind_map)
    verification = engine.run_verification(signals, start=start, end=end)

    _print_strategy_table(verification)

    matrix, names = overlay_matrix(signals, candles, kind_map, start, end, config.hold_days)
    _print_overlay(matrix, names)

    # 权重推导 + 组合对比
    weights = derive_weights(verification, HEADLINE_HOLD)
    print(f"\n{'='*100}")
    print(f"【3】权重推导：weight = max(0, {HEADLINE_HOLD}日超额胜率)，单位 pp")
    print(f"{'='*100}")
    for name, w in weights.items():
        print(f"    {name:<16s} {w*100:+.1f}pp → 权重 {w:.3f}")

    print(f"\n【4】组合回测：等权 vs 加权")
    print(f"{'─'*100}")
    eq_cfg = BacktestConfig()
    eq_report = engine.run_portfolio(signals)
    _print_portfolio("等权", eq_report)

    w_cfg = BacktestConfig()
    w_cfg.portfolio.strategy_weights = weights
    w_engine = BacktestEngine(DictCandlesProvider(candles), w_cfg, kind_map=kind_map)
    w_report = w_engine.run_portfolio(signals)
    _print_portfolio("加权", w_report)

    if args.out:
        payload = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "total_signals": len(signals),
            "verification": verification.model_dump(mode="json"),
            "overlay_matrix": {f"{a}×{b}": v for (a, b), v in matrix.items()},
            "weights": weights,
            "portfolio_equal": eq_report.model_dump(mode="json"),
            "portfolio_weighted": w_report.model_dump(mode="json"),
        }
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结果已写入 {args.out}")


if __name__ == "__main__":
    main()
