#!/usr/bin/env python3
"""组合权重情景对比：从缓存信号出发，跑多组权重，验证「加权是否改善组合」。

依赖 scripts/run_signal_overlay.py 生成的 data/signals_cache.pkl（先跑一次全量扫描）。
本脚本只读缓存 + 全市场 K 线，几秒内跑完多组组合，对比总收益/最大回撤/夏普。

情景：
    equal     等权（每信号 20% 全额，旧行为）
    win_rate  按 20 日超额胜率推导：max(0, excess_win_rate) 归一化
    return    按 20 日超额收益推导：max(0, excess_return) 归一化
    etf_only  只给 etf_accumulation 权重（其余 0）
    stealth_only 只给 stealth_rally 权重（其余 0）
    etf_stealth  etf + stealth 两策略（按超额收益比例）

用法：
    .venv/bin/python scripts/portfolio_weight_scenarios.py
"""

from __future__ import annotations

import pickle
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.config import BacktestConfig
from backtest.engine import BacktestEngine, DictCandlesProvider
from datasource.tdx import resolve_hsjday_root
from strategies import REGISTRY
from strategies.filters import SymbolKind, filter_for_kinds
from strategies.scanner import MarketScanner

CACHE = ROOT / "data" / "signals_cache.pkl"
HEADLINE_HOLD = 20


def load_universe(end: date):
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


def strategy_metrics(signals, candles, kind_map, start, end):
    """跑一次验证，返回 {strategy: {excess_win_rate_20d, excess_return_20d}}。"""
    engine = BacktestEngine(DictCandlesProvider(candles), BacktestConfig(), kind_map=kind_map)
    verification = engine.run_verification(signals, start=start, end=end)
    out = {}
    for sr in verification.by_strategy:
        hold = next((h for h in sr.holds if h.hold_days == HEADLINE_HOLD), None)
        out[sr.strategy] = {
            "excess_win_rate": hold.excess_win_rate if hold else None,
            "excess_return": hold.excess_return if hold else None,
        }
    return out


def run_scenario(name, weights, signals, candles, kind_map):
    cfg = BacktestConfig()
    cfg.portfolio.strategy_weights = weights
    engine = BacktestEngine(DictCandlesProvider(candles), cfg, kind_map=kind_map)
    report = engine.run_portfolio(signals)
    sharpe = f"{report.sharpe:.3f}" if report.sharpe is not None else "—"
    print(
        f"    {name:<14s} 总收益 {report.total_return*100:+7.2f}%  "
        f"最大回撤 {report.max_drawdown*100:7.2f}%  夏普 {sharpe:>7s}  "
        f"建仓 {report.filled_buys:>5d} 成交 {report.trade_count:>5d}"
    )
    return report


def main() -> None:
    start = date(2026, 3, 1)
    end = date(2026, 8, 27)

    with open(CACHE, "rb") as f:
        signals = pickle.load(f)

    print("加载全市场 K 线...", flush=True)
    candles, kind_map = load_universe(end)
    print(f"已加载 {len(candles)} 只，信号 {len(signals)} 条", flush=True)

    metrics = strategy_metrics(signals, candles, kind_map, start, end)
    print(f"\n{'='*100}")
    print(f"各策略 20 日超额（推导权重用）")
    for name, m in metrics.items():
        exw = f"{m['excess_win_rate']*100:+.1f}pp" if m["excess_win_rate"] is not None else "—"
        exr = f"{m['excess_return']*100:+.2f}%" if m["excess_return"] is not None else "—"
        print(f"    {name:<16s} 超额胜率 {exw:>9s}  超额收益 {exr:>9s}")

    # 各权重情景
    win_w = {n: max(0.0, m["excess_win_rate"] or 0.0) for n, m in metrics.items()}
    ret_w = {n: max(0.0, m["excess_return"] or 0.0) for n, m in metrics.items()}
    etf_only = {n: (1.0 if n == "etf_accumulation" else 0.0) for n in metrics}
    stealth_only = {n: (1.0 if n == "stealth_rally" else 0.0) for n in metrics}
    etf_stealth = {
        n: (ret_w[n] if n in ("etf_accumulation", "stealth_rally") else 0.0)
        for n in metrics
    }

    print(f"\n{'='*100}")
    print("组合回测情景对比")
    print(f"{'─'*100}")
    run_scenario("equal(等权)", None, signals, candles, kind_map)
    run_scenario("win_rate加权", win_w, signals, candles, kind_map)
    run_scenario("return加权", ret_w, signals, candles, kind_map)
    run_scenario("etf_only", etf_only, signals, candles, kind_map)
    run_scenario("stealth_only", stealth_only, signals, candles, kind_map)
    run_scenario("etf_stealth", etf_stealth, signals, candles, kind_map)


if __name__ == "__main__":
    main()
