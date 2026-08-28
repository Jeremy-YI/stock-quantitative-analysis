#!/usr/bin/env python3
"""regime 分策略配置 + 三参数网格搜索（阶段 8 遗留 TODO #1）。

阶段 8 实测：默认 filter 对均值回归类有效（macd_volume_washout 损失收窄）、对
深跌吸筹类有害（etf_accumulation 从 +1.99% 变 -2.42%，因为它需要的深回撤被挡掉）。
本脚本：

    1. 在样本内（IS 2026-03~08）对两类策略分别做 regime 三参数网格搜索，找最优阈值；
    2. 在样本内 + 三段样本外对比「无 filter / 全局 filter / 分策略 filter」。

网格搜索（严格在样本内做，样本外只验证，避免又一轮过拟合）：
    max_index_20d_return ∈ {0.00, 0.02, 0.04, 0.08, 0.15, 1.0}
    max_activity         ∈ {0.8, 1.0, 1.2, 1.5, 3.0}
    min_drawdown         ∈ {-0.08, -0.15, -0.25, -0.40, -1.0}
    max_drawdown         固定 0.0

目标函数 = 组合总收益（策略在弱市里大多是负绝对收益，故等价于「损失最小化」），
同时报告夏普/最大回撤。分策略 filter 用 market.regime.REGIME_PROFILES 的档位映射。

用法（仓库根目录）：
    .venv/bin/python scripts/run_regime_grid.py --out data/regime_grid.json
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

from backtest.config import BacktestConfig, RegimeFilterConfig
from backtest.portfolio import simulate_portfolio
from datasource.tdx import resolve_hsjday_root
from market.calendar import trading_days
from market.regime import compute_market_series
from strategies.filters import SymbolKind, filter_for_kinds
from strategies.scanner import MarketScanner

HSJDAY = resolve_hsjday_root()
SIGNALS_CACHE = ROOT / "data" / "signals_cache.pkl"
WASHOUT_CACHE = ROOT / "data" / "macd_volume_washout_signals.pkl"

# 两类策略的代表（均值回归 / 深跌吸筹）
CLASS_REPRESENTATIVE = {"mean_reversion": "macd_volume_washout", "deep_accumulation": "etf_accumulation"}

# 网格
_R20_GRID = [0.00, 0.02, 0.04, 0.08, 0.15, 1.0]
_ACT_GRID = [0.8, 1.0, 1.2, 1.5, 3.0]
_DD_GRID = [-0.08, -0.15, -0.25, -0.40, -1.0]


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


def load_is_signals() -> list:
    signals = list(pickle.load(open(SIGNALS_CACHE, "rb")))
    if WASHOUT_CACHE.exists():
        signals.extend(pickle.load(open(WASHOUT_CACHE, "rb")))
    return signals


def solo_signals(signals: list, strategy: str) -> list:
    return [s for s in signals if s.strategy == strategy]


def run_solo(signals, candles, series, filter_cfg, stepwise=None):
    """跑单策略组合（无权重 = 该策略独占），返回 (total_return, max_drawdown, sharpe, filled)。"""
    cfg = BacktestConfig()
    weights = {s.strategy for s in signals}
    cfg.portfolio.strategy_weights = {w: 1.0 for w in weights}
    if filter_cfg is not None:
        cfg.portfolio.regime_by_strategy = {w: filter_cfg for w in weights}
    if stepwise is not None:
        cfg.portfolio.stepwise_tranches = stepwise
    # 只传被信号引用的蜡烛（市场序列已单独算），避免每档网格重建全市场映射
    used = {s.symbol for s in signals}
    slim = {sym: candles[sym] for sym in used if sym in candles}
    raw = simulate_portfolio(signals, slim, cfg, regime_series=series)
    return raw["total_return"], raw["max_drawdown"], raw["sharpe"], raw["filled_buys"]


def grid_search(signals, candles, series, label: str) -> dict:
    """对单策略做三参数网格搜索，返回最优阈值组合 + 全部结果（用于观察平台）。"""
    best = None
    results = []
    for r20 in _R20_GRID:
        for act in _ACT_GRID:
            for dd in _DD_GRID:
                f = RegimeFilterConfig(
                    max_index_20d_return=r20, max_activity=act,
                    min_drawdown=dd, max_drawdown=0.0,
                )
                tr, mdd, shp, filled = run_solo(signals, candles, series, f)
                results.append({"r20": r20, "act": act, "dd": dd,
                                "total_return": round(tr, 4), "max_drawdown": round(mdd, 4),
                                "sharpe": round(shp, 4) if shp is not None else None,
                                "filled": filled})
                score = tr  # 目标：总收益最大（损失最小）
                if best is None or score > best["total_return"]:
                    best = {"r20": r20, "act": act, "dd": dd, "total_return": tr,
                            "max_drawdown": mdd, "sharpe": shp, "filled": filled}
    return {"label": label, "best": best, "results": results}


def _fmt3(cfg, signals, candles, series, stepwise=None):
    tr, mdd, shp, filled = run_solo(signals, candles, series, cfg, stepwise)
    shp_s = "—" if shp is None else f"{shp:.3f}"
    return f"收益 {tr*100:+7.2f}%  回撤 {mdd*100:7.2f}%  夏普 {shp_s:>7s}  建仓 {filled:>5d}"


def main() -> None:
    parser = argparse.ArgumentParser(description="regime 分策略配置 + 网格搜索")
    parser.add_argument("--out", default="data/regime_grid.json")
    parser.add_argument("--grid-only", action="store_true", help="只做样本内网格搜索，不做 OOS 验证")
    args = parser.parse_args()

    print("加载样本内信号 + 全市场 K 线...", flush=True)
    signals = load_is_signals()
    candles, kind_map = load_universe(date(2026, 8, 27))
    stock_candles = {s: df for s, df in candles.items() if kind_map.get(s) in (SymbolKind.STOCK, SymbolKind.STOCK.value)}
    series = compute_market_series(stock_candles)
    print("  信号 %d 条，K 线 %d 只，市场序列 %d 日" % (len(signals), len(candles), len(series)), flush=True)

    out: dict = {"grid": {}, "compare": {}}
    for cls, strat in CLASS_REPRESENTATIVE.items():
        ss = solo_signals(signals, strat)
        print("\n【网格搜索 %s（%s，样本内 IS）】%d 条信号" % (cls, strat, len(ss)), flush=True)
        g = grid_search(ss, candles, series, cls)
        out["grid"][cls] = {"strategy": strat, "best": g["best"]}
        b = g["best"]
        print("  最优：r20<%+.2f  活跃<%.1f  回撤>%+.2f  → 收益 %+.2f%%  回撤 %.2f%%  夏普 %s"
              % (b["r20"], b["act"], b["dd"], b["total_return"]*100, b["max_drawdown"]*100,
                 "—" if b["sharpe"] is None else f"{b['sharpe']:.3f}"))

    # 样本内对比：无 / 全局 / 分策略
    print("\n" + "=" * 90)
    print("样本内（IS）组合回测对比：无 filter / 全局 filter / 分策略 filter")
    print("=" * 90)
    compare = {}
    for strat in ("macd_volume_washout", "etf_accumulation"):
        ss = solo_signals(signals, strat)
        global_f = RegimeFilterConfig()  # 默认均值回归档
        # 分策略：均值回归类用 mean_reversion 档，深跌吸筹类用 deep_accumulation 档
        prof = "mean_reversion" if strat == "macd_volume_washout" else "deep_accumulation"
        per_f = RegimeFilterConfig.from_profile(prof)
        row = {
            "none": _fmt3(None, ss, candles, series),
            "global": _fmt3(global_f, ss, candles, series),
            "per_strategy": _fmt3(per_f, ss, candles, series),
        }
        compare[strat] = row
        print("\n【%s】" % strat)
        print("  无 filter       %s" % row["none"])
        print("  全局 filter     %s" % row["global"])
        print("  分策略 filter   %s" % row["per_strategy"])
    out["compare"]["IS"] = compare

    # 样本外验证（读 OOS 信号缓存，若已生成）
    if not args.grid_only:
        oos_windows = {"OOS-A": "2023-12-31", "OOS-B": "2024-12-31", "OOS-C": "2026-02-28"}
        for wlabel, wend in oos_windows.items():
            cache = ROOT / "data" / ("oos_signals_%s.pkl" % wlabel.lower())
            if not cache.exists():
                print("\n[%s] 信号缓存未生成，跳过 OOS 验证" % wlabel)
                continue
            wsignals = pickle.load(open(cache, "rb"))
            wcandles, wkind = load_universe(date.fromisoformat(wend))
            wstock = {s: df for s, df in wcandles.items() if wkind.get(s) in (SymbolKind.STOCK, SymbolKind.STOCK.value)}
            wseries = compute_market_series(wstock)
            print("\n" + "=" * 90)
            print("样本外（%s）组合回测对比" % wlabel)
            print("=" * 90)
            cw = {}
            for strat in ("macd_volume_washout", "etf_accumulation"):
                ss = solo_signals(wsignals, strat)
                if not ss:
                    cw[strat] = {"none": "无信号"}
                    continue
                global_f = RegimeFilterConfig()
                prof = "mean_reversion" if strat == "macd_volume_washout" else "deep_accumulation"
                per_f = RegimeFilterConfig.from_profile(prof)
                cw[strat] = {
                    "none": _fmt3(None, ss, wcandles, wseries),
                    "global": _fmt3(global_f, ss, wcandles, wseries),
                    "per_strategy": _fmt3(per_f, ss, wcandles, wseries),
                }
                print("\n【%s】" % strat)
                print("  无 filter       %s" % cw[strat]["none"])
                print("  全局 filter     %s" % cw[strat]["global"])
                print("  分策略 filter   %s" % cw[strat]["per_strategy"])
            out["compare"][wlabel] = cw

    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n结构化快照已写入 %s" % args.out)


if __name__ == "__main__":
    main()
