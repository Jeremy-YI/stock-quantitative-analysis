#!/usr/bin/env python3
"""市场环境（regime）过滤前后对比：组合总收益 / 最大回撤 / 夏普（阶段 8 核心数字）。

复用 data/signals_cache.pkl（六策略信号），跑三组对比：
    1. 等权组合：无 regime filter vs 默认 regime filter
    2. etf_only 组合：无 filter vs 默认 filter
    3. 超额收益加权组合：无 filter vs 默认 filter

默认 filter（docs/市场环境模块说明.md）：
    大盘 20 日涨幅 < +4% 且 活跃度 < 1.2 且 回撤在 -15%~0。

用法（仓库根目录）：

    .venv/bin/python scripts/run_regime_filter.py --start 2026-03-01 --end 2026-08-27
"""

from __future__ import annotations

import argparse
import pickle
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.config import BacktestConfig, RegimeFilterConfig
from backtest.engine import BacktestEngine, DictCandlesProvider
from datasource.tdx import resolve_hsjday_root
from market.regime import compute_market_series, snapshot_at
from market.calendar import trading_days
from strategies.filters import SymbolKind, filter_for_kinds
from strategies.scanner import MarketScanner

HSJDAY = resolve_hsjday_root()
SIGNALS_CACHE = ROOT / "data" / "signals_cache.pkl"


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


def _run(cfg: BacktestConfig, signals, candles, kind_map) -> dict:
    engine = BacktestEngine(DictCandlesProvider(candles), cfg, kind_map=kind_map)
    return engine.run_portfolio(signals)


def _fmt(r) -> str:
    sharpe = f"{r.sharpe:.3f}" if r.sharpe is not None else "—"
    return (
        f"总收益 {r.total_return*100:+7.2f}%  最大回撤 {r.max_drawdown*100:7.2f}%  "
        f"夏普 {sharpe:>7s}  建仓 {r.filled_buys:>5d}  成交 {r.trade_count:>5d}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="regime 过滤前后组合对比")
    parser.add_argument("--start", default="2026-03-01")
    parser.add_argument("--end", default="2026-08-27")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    with open(SIGNALS_CACHE, "rb") as f:
        signals = pickle.load(f)
    print(f"加载全市场 K 线...", flush=True)
    candles, kind_map = load_universe(end)
    print(f"已加载 {len(candles)} 只，信号 {len(signals)} 条", flush=True)

    # 市场环境序列（仅个股宇宙，与引擎内部计算一致）
    stock_candles = {
        sym: df for sym, df in candles.items()
        if kind_map.get(sym) in (SymbolKind.STOCK, SymbolKind.STOCK.value)
    }
    series = compute_market_series(stock_candles)

    # 打印当前（末日）regime 与允许状态
    last_day = trading_days(start, end)[-1]
    snap = snapshot_at(series, last_day)
    if snap is not None:
        f = RegimeFilterConfig()
        allowed = f.allow(snap.index_20d_return, snap.activity, snap.drawdown)
        print(
            f"\n末日 regime（{last_day}）：大盘20日 {snap.index_20d_return*100:+.2f}% "
            f"({snap.labels['index_20d']})，活跃度 {snap.activity:.2f} ({snap.labels['activity']})，"
            f"回撤 {snap.drawdown*100:+.2f}% ({snap.labels['drawdown']}) → "
            f"{'允许开仓' if allowed else '不允许开仓'}"
        )

    print(f"\n{'='*100}")
    print(f"组合回测：regime 过滤前后对比（{start} ~ {end}）")
    print(f"{'='*100}")

    # 等权
    eq = BacktestConfig()
    eq_filtered = BacktestConfig()
    eq_filtered.portfolio.regime_filter = RegimeFilterConfig()
    print(f"\n【等权组合】")
    print(f"  无 filter   {_fmt(_run(eq, signals, candles, kind_map))}")
    print(f"  有 filter   {_fmt(_run(eq_filtered, signals, candles, kind_map))}")

    # etf_only
    etf_w = {n: (1.0 if n == "etf_accumulation" else 0.0) for n in {s.strategy for s in signals}}
    etf = BacktestConfig()
    etf.portfolio.strategy_weights = etf_w
    etf_filtered = BacktestConfig()
    etf_filtered.portfolio.strategy_weights = etf_w
    etf_filtered.portfolio.regime_filter = RegimeFilterConfig()
    print(f"\n【etf_accumulation 独占组合】")
    print(f"  无 filter   {_fmt(_run(etf, signals, candles, kind_map))}")
    print(f"  有 filter   {_fmt(_run(etf_filtered, signals, candles, kind_map))}")


if __name__ == "__main__":
    main()
