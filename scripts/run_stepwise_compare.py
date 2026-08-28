#!/usr/bin/env python3
"""3-2-2-2 分步建仓 vs 一次性建仓对比（阶段 9，对应 TOOLS.md 仓位纪律）。

TOOLS.md / MEMORY.md 仓位规则（只读）：
    - 个股单只 ≤ 20%
    - 3-2-2-2 分步建仓（首仓 30%，后续三次各 20%，合计 90%，留 10% 预备）
    - 永远保留预备队（最多动用 80% 资金）

本脚本对比「一次性建仓」与「3-2-2-2 分步建仓」的总收益 / 最大回撤 / 夏普差异，
在样本内（IS）+ 三段样本外（若信号缓存已生成）上跑。

实现：PortfolioConfig.stepwise_tranches=None（一次性）vs (0.3, 0.2, 0.2, 0.2)（分步）。
分步节奏 = 入场后每 stepwise_interval_days 个交易日加一档（默认 1 日）。

用法（仓库根目录）：
    .venv/bin/python scripts/run_stepwise_compare.py --out data/stepwise_compare.json
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.config import BacktestConfig
from backtest.portfolio import simulate_portfolio
from datasource.tdx import resolve_hsjday_root
from market.regime import compute_market_series
from strategies.filters import SymbolKind, filter_for_kinds
from strategies.scanner import MarketScanner

HSJDAY = resolve_hsjday_root()
SIGNALS_CACHE = ROOT / "data" / "signals_cache.pkl"
WASHOUT_CACHE = ROOT / "data" / "macd_volume_washout_signals.pkl"

# 默认策略权重（docs/信号叠加分析.md：etf 主配 + 偷涨次配，超额收益推导）
WEIGHTS = {"etf_accumulation": 6.25, "stealth_rally": 1.65}

STEPWISE = (0.3, 0.2, 0.2, 0.2)


def load_universe(end: date):
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


def load_is_signals() -> list:
    signals = list(pickle.load(open(SIGNALS_CACHE, "rb")))
    if WASHOUT_CACHE.exists():
        signals.extend(pickle.load(open(WASHOUT_CACHE, "rb")))
    return signals


def run(signals, candles, series, stepwise):
    cfg = BacktestConfig()
    cfg.portfolio.strategy_weights = dict(WEIGHTS)
    if stepwise is not None:
        cfg.portfolio.stepwise_tranches = stepwise
    # 只把「被信号引用」的标的蜡烛传给组合模拟（市场序列已单独算），
    # 避免对全市场 7000 只重建开/收价映射（每次约 1~2s）。
    used = {s.symbol for s in signals if s.strategy in WEIGHTS}
    slim = {sym: candles[sym] for sym in used if sym in candles}
    raw = simulate_portfolio(signals, slim, cfg, regime_series=series)
    return raw


def _fmt(raw) -> str:
    shp = "—" if raw["sharpe"] is None else f"{raw['sharpe']:.3f}"
    return (f"收益 {raw['total_return']*100:+7.2f}%  回撤 {raw['max_drawdown']*100:7.2f}%  "
            f"夏普 {shp:>7s}  建仓 {raw['filled_buys']:>5d}  成交 {raw['trade_count']:>5d}")


def _window(label, signals, candles, kind_map, out):
    stock = {s: df for s, df in candles.items()
             if kind_map.get(s) in (SymbolKind.STOCK, SymbolKind.STOCK.value)}
    series = compute_market_series(stock)
    one = run(signals, candles, series, None)
    step = run(signals, candles, series, STEPWISE)
    out[label] = {"one_shot": _fmt(one), "stepwise_3_2_2_2": _fmt(step),
                  "one_shot_raw": {"total_return": one["total_return"], "max_drawdown": one["max_drawdown"],
                                   "sharpe": one["sharpe"], "filled_buys": one["filled_buys"]},
                  "stepwise_raw": {"total_return": step["total_return"], "max_drawdown": step["max_drawdown"],
                                   "sharpe": step["sharpe"], "filled_buys": step["filled_buys"]}}
    print("\n【%s】" % label)
    print("  一次性建仓      %s" % out[label]["one_shot"])
    print("  3-2-2-2 分步     %s" % out[label]["stepwise_3_2_2_2"])


def main() -> None:
    parser = argparse.ArgumentParser(description="3-2-2-2 vs 一次性建仓")
    parser.add_argument("--out", default="data/stepwise_compare.json")
    args = parser.parse_args()

    out: dict = {}

    print("加载样本内信号...", flush=True)
    signals = load_is_signals()
    candles, kind_map = load_universe(date(2026, 8, 27))
    _window("IS", signals, candles, kind_map, out)

    for wlabel, wend in (("OOS-A", "2023-12-31"), ("OOS-B", "2024-12-31"), ("OOS-C", "2026-02-28")):
        cache = ROOT / "data" / ("oos_signals_%s.pkl" % wlabel.lower())
        if not cache.exists():
            print("\n[%s] 信号缓存未生成，跳过" % wlabel)
            continue
        ws = pickle.load(open(cache, "rb"))
        wc, wk = load_universe(date.fromisoformat(wend))
        _window(wlabel, ws, wc, wk, out)

    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n结构化快照已写入 %s" % args.out)


if __name__ == "__main__":
    main()
