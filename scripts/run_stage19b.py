#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 19b：活跃市值「两次 -2.3」触发器 + regime 切换回测。

Jeremy 2026-08-30 确认口径：
  - 触发器：活跃市值「单日跌幅 ≥ 2.3%」出现两次（不限间隔）→ 切低波红利（risk-off）
  - 活跃市值上升区间 → 买热门板块（risk-on）
  - 「大跌要敢买」→ 深跌后回补（本版用对称「单日涨≥2.3%两次」作回升确认的占位）

活跃市值(OAMV) 是指南针专有（存量市值，慢变量），本地无数据。本版用两个代理：
  1. 全市场等权指数（等权日收益，广度加权，最接近「活跃股票市值之和」）
  2. 上证指数（市场晴雨表，作敏感性对照）

篮子：成长=半导体成分（sector_stocks.json）、红利=中证红利 000922，均等权前复权。
切换：触发日收盘生效，次日持有新篮子（无前视）。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datasource.tdx.reader import resolve_hsjday_root, resolve_symbol_path, parse_day_file
from market.adjust import forward_adjust_frame
from scripts.run_stage16 import list_stock_symbols

PERIOD_START = date(2020, 1, 1)
PERIOD_END = date(2026, 8, 28)
DROP = 0.023  # 单日跌幅 ≥ 2.3%


def basket_daily(codes, root):
    acc = {}
    for code in codes:
        try:
            df = parse_day_file(resolve_symbol_path(root, code))
        except FileNotFoundError:
            continue
        if len(df) < 60:
            continue
        df = forward_adjust_frame(df, code)
        c = df["close"].astype(float).to_numpy()
        r = np.diff(c) / c[:-1]
        for d, rr in zip(df["date"].to_numpy()[1:], r):
            acc.setdefault(d, []).append(rr)
    idx = sorted(acc)
    return pd.Series([float(np.mean(acc[d])) for d in idx], index=idx)


def equal_weight_index_daily(root, symbols, limit=None):
    """全市场等权日收益（所有 hs 个股均值）。"""
    acc = {}
    for i, code in enumerate(symbols):
        try:
            df = parse_day_file(resolve_symbol_path(root, code))
        except FileNotFoundError:
            continue
        if len(df) < 60:
            continue
        c = df["close"].astype(float).to_numpy()
        r = np.diff(c) / c[:-1]
        for d, rr in zip(df["date"].to_numpy()[1:], r):
            acc.setdefault(d, []).append(rr)
        if limit and i + 1 >= limit:
            break
    idx = sorted(acc)
    return pd.Series([float(np.mean(acc[d])) for d in idx], index=idx)


def regime_from_series(ret: pd.Series) -> np.ndarray:
    """两次 -2.3% → risk_off；两次 +2.3% → risk_on。返回 bool 数组（True=risk_on）。"""
    idx = ret.index
    n = len(idx)
    state = True
    crash = 0
    surge = 0
    out = np.ones(n, dtype=bool)
    for i in range(n):
        out[i] = state
        v = float(ret.iloc[i])
        if state:  # risk_on，数大跌
            if v <= -DROP:
                crash += 1
                if crash >= 2:
                    state = False
                    crash = 0
                    surge = 0
            else:
                # 不重置 crash（「不限间隔」），但用 surge 复位？保持累计
                pass
        else:  # risk_off，数大涨
            if v >= DROP:
                surge += 1
                if surge >= 2:
                    state = True
                    surge = 0
                    crash = 0
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/stage19b_results.json")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    root = resolve_hsjday_root()

    # 篮子
    idx = json.loads((ROOT / "data" / "stage18_index_universes.json").read_text())
    div_codes = sorted(idx["000922"]["stocks"])
    sec = json.loads(Path("/Users/yanhongyi/Documents/Obsidian Vault/大富翁/A股/A持仓-复盘/A每日复盘/板块资金流向/sector_stocks.json").read_text())
    semi_codes = sorted(sec["半导体"]["stocks"])

    div_r = basket_daily(div_codes, root)
    semi_r = basket_daily(semi_codes, root)

    # 上证指数日收益
    sh = parse_day_file(root / "sh" / "lday" / "sh000001.day").set_index("date")["close"].astype(float)
    sh_ret = sh.pct_change().dropna()

    # 全市场等权
    symbols = list_stock_symbols(root, "hs")
    ew_ret = equal_weight_index_daily(root, symbols, limit=args.limit)

    results = {"meta": {"period": [str(PERIOD_START), str(PERIOD_END)],
                        "drop": DROP, "generated_at": pd.Timestamp.now().isoformat()},
               "proxies": {}}

    for name, ret in (("上证指数", sh_ret), ("全市场等权", ew_ret)):
        # 对齐到公共日历（篮子日收益的日期）
        cal = sorted(set(ret.index) & set(div_r.index) & set(semi_r.index)
                     & {d for d in ret.index if PERIOD_START <= d <= PERIOD_END})
        n = len(cal)
        rg = regime_from_series(ret.reindex(cal))
        dr = div_r.reindex(cal).fillna(0).to_numpy()
        sr = semi_r.reindex(cal).fillna(0).to_numpy()
        strat = np.where(rg, sr, dr)

        def cum(r):
            return float(np.prod(1.0 + r) - 1.0)
        def dd(r):
            eq = np.cumprod(1.0 + r)
            return float(np.min(eq / np.maximum.accumulate(eq) - 1.0))

        results["proxies"][name] = {
            "n_days": n,
            "n_switches": int(np.sum(np.diff(rg.astype(int)) != 0)),
            "time_risk_on": float(np.mean(rg)),
            "cumulative": {"switch": cum(strat), "always_semi": cum(sr),
                           "always_div": cum(dr)},
            "annualized": {"switch": float((1 + cum(strat)) ** (252.0 / n) - 1),
                           "always_semi": float((1 + cum(sr)) ** (252.0 / n) - 1),
                           "always_div": float((1 + cum(dr)) ** (252.0 / n) - 1)},
            "max_drawdown": {"switch": dd(strat), "always_semi": dd(sr),
                             "always_div": dd(dr)},
        }

    (ROOT / args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    for name, p in results["proxies"].items():
        print("==== 活跃市值代理：%s ====" % name)
        print("  切换次数 %d，risk_on 时间占比 %.0f%%" % (p["n_switches"], p["time_risk_on"] * 100))
        print("  累积：切换 %+.1f%% | 一直半导体 %+.1f%% | 一直红利 %+.1f%%" %
              (p["cumulative"]["switch"] * 100, p["cumulative"]["always_semi"] * 100,
               p["cumulative"]["always_div"] * 100))
        print("  年化：切换 %+.1f%% | 半导体 %+.1f%% | 红利 %+.1f%%" %
              (p["annualized"]["switch"] * 100, p["annualized"]["always_semi"] * 100,
               p["annualized"]["always_div"] * 100))
        print("  回撤：切换 %+.1f%% | 半导体 %+.1f%% | 红利 %+.1f%%" %
              (p["max_drawdown"]["switch"] * 100, p["max_drawdown"]["always_semi"] * 100,
               p["max_drawdown"]["always_div"] * 100))
        print()


if __name__ == "__main__":
    main()
