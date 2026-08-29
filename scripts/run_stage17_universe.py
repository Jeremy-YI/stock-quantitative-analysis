#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 17 任务 1：构建可信的 ETF 宇宙（流动性过滤 + 相关性去重 + 分组）。

口径（见 docs/阶段17-进度.md）：
- ETF 定义 = classify_symbol == SymbolKind.ETF（sh 510/511/512/513/515/516/517/518/520/560/561/562/563/588；
  sz 159）。
- 流动性 = 滚动 60 日平均成交额（.day 的 amount 字段，单位元），阈值测 3000万/5000万/1亿。
- 去重 = 滚动 60 日日收益两两 Pearson 相关聚簇，阈值测 0.90/0.95/0.98，每簇保留滚动成交额最大一只。
- 重平衡 = 每月首个交易日（point-in-time，只用重平衡日及之前的数据定当月宇宙）。

用法：
    .venv/bin/python scripts/run_stage17_universe.py --out data/stage17_universe.json
"""
from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datasource.tdx.reader import parse_day_file, resolve_hsjday_root
from market.adjust import forward_adjust_frame
from strategies.filters import SymbolKind, classify_symbol

PANEL_START = date(2019, 1, 1)   # 面板回看起点（给 60 日相关窗口 + 120 根前置留 warmup）
PERIOD_START = date(2020, 1, 1)  # 重平衡/回测起点
PERIOD_END = date(2026, 8, 28)
LIQ_THRESHOLDS = (3e7, 5e7, 1e8)   # 3000万 / 5000万 / 1亿（元）
RHO_THRESHOLDS = (0.90, 0.95, 0.98)
MIN_HIST_BARS = 120
LIQ_WINDOW = 60
CORR_WINDOW = 60


def list_etf_symbols(root: Path) -> list[tuple[str, str, Path]]:
    """返回 [(market, code, path), ...]，market ∈ sh/sz，code 为 6 位代码。"""
    out = []
    for m in ("sh", "sz"):
        lday = root / m / "lday"
        if not lday.is_dir():
            continue
        for fn in sorted(lday.iterdir()):
            if not fn.name.endswith(".day"):
                continue
            code = fn.name[2:8]
            if len(code) != 6:
                continue
            if classify_symbol(m, code) == SymbolKind.ETF:
                out.append((m, code, fn))
    return out


def master_calendar(root: Path) -> tuple[np.ndarray, np.ndarray]:
    """上证指数交易日历（2019-01-01 ~ 2026-08-28，前段作 warmup），返回 (date 数组, ordinal 数组)。"""
    sse = parse_day_file(root / "sh" / "lday" / "sh000001.day")
    ords = np.array([d.toordinal() for d in sse["date"].to_numpy()], dtype=np.int64)
    lo, hi = PANEL_START.toordinal(), PERIOD_END.toordinal()
    m = (ords >= lo) & (ords <= hi)
    return sse["date"].to_numpy()[m], ords[m]


class UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def cluster_corr(corr: np.ndarray, rho: float) -> list[list[int]]:
    """把相关矩阵按阈值 rho 聚成连通分量（每簇 = 索引列表）。"""
    n = corr.shape[0]
    uf = UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            c = corr[i, j]
            if np.isfinite(c) and c >= rho:
                uf.union(i, j)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)
    return list(groups.values())


def build_panels(root: Path, cal_ord: np.ndarray) -> dict:
    """构建 cal_ret / cal_amt60 / cal_nbars 三个 (ncal, n_etf) 面板 + 元信息。"""
    cal_dates = [date.fromordinal(int(o)) for o in cal_ord]
    ncal = len(cal_ord)
    syms = list_etf_symbols(root)
    n_etf = len(syms)

    cal_ret = np.full((ncal, n_etf), np.nan, dtype=np.float64)
    cal_amt60 = np.full((ncal, n_etf), np.nan, dtype=np.float64)
    cal_nbars = np.zeros((ncal, n_etf), dtype=np.int32)

    meta = {"symbols": [m + c for m, c, _ in syms], "n": n_etf}
    for i, (m, code, path) in enumerate(syms):
        try:
            df = parse_day_file(path)
        except FileNotFoundError:
            continue
        if df.empty:
            continue
        df = forward_adjust_frame(df, m + code)
        own_dates = df["date"].to_numpy()
        own_ord = np.array([d.toordinal() for d in own_dates], dtype=np.int64)

        close = df["close"].astype(float).to_numpy()
        amount = df["amount"].astype(float).to_numpy()

        # 日收益（对齐到公共日历，停牌日 ffill → 0 收益）
        cs = pd.Series(close, index=own_dates)
        cs = cs.reindex(cal_dates).ffill()
        ret = cs.pct_change().to_numpy(dtype=float)  # 上市前 NaN，停牌日 0

        # 滚动 60 日平均成交额（own bars 上算，再对齐日历 ffill）
        amt60_own = pd.Series(amount).rolling(LIQ_WINDOW, min_periods=LIQ_WINDOW).mean().to_numpy()
        as_ = pd.Series(amt60_own, index=own_dates).reindex(cal_dates).ffill()

        cal_ret[:, i] = ret
        cal_amt60[:, i] = as_.to_numpy(dtype=float)
        cal_nbars[:, i] = np.searchsorted(own_ord, cal_ord, side="right").astype(np.int32)

    return {"cal_ret": cal_ret, "cal_amt60": cal_amt60, "cal_nbars": cal_nbars, "meta": meta}


def rebalance_dates(cal_ord: np.ndarray) -> list[int]:
    """每月首个交易日、且在 2020-01-01 之后的日历索引（前段只做 warmup）。"""
    dates = [date.fromordinal(int(o)) for o in cal_ord]
    out = []
    last_key = None
    for t, d in enumerate(dates):
        if d < PERIOD_START:
            continue
        key = (d.year, d.month)
        if key != last_key:
            out.append(t)
            last_key = key
    return out


def build_universe(panels: dict, cal_ord: np.ndarray, liq_thr: float, rho: float) -> dict:
    cal_ret = panels["cal_ret"]
    cal_amt60 = panels["cal_amt60"]
    cal_nbars = panels["cal_nbars"]
    ncal, n_etf = cal_ret.shape
    syms = panels["meta"]["symbols"]

    reb = rebalance_dates(cal_ord)
    rebalances = []
    ever_in = {}  # sym -> [first_reb, last_reb, max_cluster_size]

    for R in reb:
        # 活跃：≥120 根前置 + 流动性达标 + 相关窗口内无 NaN
        hist_ok = cal_nbars[R] >= MIN_HIST_BARS
        liq_ok = cal_amt60[R] >= liq_thr
        active = np.where(hist_ok & liq_ok)[0]
        if active.size == 0:
            rebalances.append({"date": str(date.fromordinal(int(cal_ord[R]))),
                               "n_active": 0, "n_clusters": 0, "reps": []})
            continue

        win = cal_ret[R - CORR_WINDOW + 1 : R + 1, active]  # (60, k)
        # 排除窗口内有 NaN 的列（数据不足）
        col_ok = ~np.isnan(win).any(axis=0)
        active = active[col_ok]
        if active.size == 0:
            rebalances.append({"date": str(date.fromordinal(int(cal_ord[R]))),
                               "n_active": 0, "n_clusters": 0, "reps": []})
            continue
        win = cal_ret[R - CORR_WINDOW + 1 : R + 1, active]

        wmean = win.mean(axis=0)
        wstd = win.std(axis=0)
        wstd_safe = np.where(wstd > 0, wstd, np.nan)
        z = (win - wmean) / wstd_safe
        corr = (z.T @ z) / CORR_WINDOW
        corr[np.isnan(corr)] = 0.0
        np.fill_diagonal(corr, 0.0)

        clusters = cluster_corr(corr, rho)
        reps = []
        for cl in clusters:
            idx = int(cl[np.argmax(cal_amt60[R, active[cl]])])
            sym = syms[active[idx]]
            amt = float(cal_amt60[R, active[idx]])
            reps.append({"code": sym, "cluster_size": len(cl), "amt60": amt})
        reps.sort(key=lambda x: -x["amt60"])

        for r in reps:
            c = r["code"]
            if c not in ever_in:
                ever_in[c] = {"first": str(date.fromordinal(int(cal_ord[R]))), "last": None,
                              "max_cluster_size": r["cluster_size"]}
            ever_in[c]["last"] = str(date.fromordinal(int(cal_ord[R])))
            ever_in[c]["max_cluster_size"] = max(ever_in[c]["max_cluster_size"], r["cluster_size"])

        rebalances.append({"date": str(date.fromordinal(int(cal_ord[R]))),
                           "n_active": int(active.size), "n_clusters": len(clusters),
                           "reps": reps})

    return {"rebalances": rebalances, "ever_in": ever_in,
            "n_rebalances": len(reb),
            "avg_active": float(np.mean([r["n_active"] for r in rebalances])),
            "avg_clusters": float(np.mean([r["n_clusters"] for r in rebalances]))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/stage17_universe.json")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    root = resolve_hsjday_root()
    t0 = time.time()
    cal_date, cal_ord = master_calendar(root)
    print("交易日历 %d 天（2019-01-01 ~ 2026-08-28，前段 warmup）" % len(cal_ord))

    panels = build_panels(root, cal_ord)
    n_etf = panels["meta"]["n"]
    print("ETF 候选 %d 只，面板构建 %.1fs" % (n_etf, time.time() - t0))

    result = {
        "meta": {
            "panel_start": str(PANEL_START), "period_start": str(PERIOD_START),
            "period_end": str(PERIOD_END),
            "n_candidates": n_etf, "liq_window": LIQ_WINDOW, "corr_window": CORR_WINDOW,
            "min_hist_bars": MIN_HIST_BARS,
            "liq_thresholds": list(LIQ_THRESHOLDS), "rho_thresholds": list(RHO_THRESHOLDS),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "combinations": {},
    }

    for liq in LIQ_THRESHOLDS:
        for rho in RHO_THRESHOLDS:
            key = "liq_%.0fM_rho_%.2f" % (liq / 1e6, rho)
            print("组合 %s ..." % key, flush=True)
            res = build_universe(panels, cal_ord, liq, rho)
            result["combinations"][key] = {
                "liq_threshold": liq, "rho": rho,
                "avg_active": res["avg_active"], "avg_clusters": res["avg_clusters"],
                "n_ever_in": len(res["ever_in"]),
                "ever_in": res["ever_in"],
                "rebalances": [{"date": r["date"], "n_active": r["n_active"],
                                "n_clusters": r["n_clusters"],
                                "reps": [{"code": x["code"], "amt60": x["amt60"],
                                          "cluster_size": x["cluster_size"]} for x in r["reps"]]}
                               for r in res["rebalances"]],
            }
            gc.collect()

    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n已写出 %s，总耗时 %.1fs" % (args.out, time.time() - t0))


if __name__ == "__main__":
    main()
