#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 18：把 deep30（+弱势过滤）限制在「ETF 成分股宇宙」上重测。

Jeremy 2026-08-30 的 B 方案：不测 ETF 载体，改测 ETF 持仓的个股（行业主题/宽基/红利风格）。

数据现实：天天基金 jjcc 接口只给前十大重仓（175 只 ETF 并集仅 501 只个股），拿不到全持仓。
全持仓 = 跟踪指数成分股。而 193 只 ETF 跟踪的指数并集 ≈ 中证全指（000985，5122 只），
≈ 全市场 5546 只的 92%——即「ETF 成分股宇宙」几乎就是全市场。

因此本阶段按梯度测 4 个宇宙：
  1. all            = 全市场（5546，对照阶段15/16）
  2. csi985         = 中证全指 000985（5122，≈ ETF 宇宙代理）
  3. hs300          = 沪深300 000300（300，大盘质量）
  4. csi_div        = 中证红利 000922（100，红利质量）

每个宇宙：deep30/deep20 × 持有 20/25/60 × （无过滤 / dir60↓ 弱势过滤），
减「全市场季度基线」（stage15 base_avg，与阶段15/16 同口径）+ 减「本宇宙季度基线」（等权）。

MAE/MFE = min(low)/max(high)（阶段12b/17 同口径）。

无前视：宇宙 = 当前快照（幸存者偏差已在阶段18说明，本阶段为第一遍近似）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datasource.tdx.reader import parse_day_file, resolve_hsjday_root, resolve_symbol_path
from market.adjust import forward_adjust_frame
from scripts.pin30_common import pin30_series
from scripts.run_stage16 import (
    PERIOD_START, PERIOD_END, HOLDS, SHORT_PIN, LONG_DEEP_MAX, MIN_HIST_BARS,
    INDEX_HS300, build_quarters, quarter_ids, binom_two_sided, list_stock_symbols,
    load_index, build_market_state,
)

SHORT_PIN20 = 20.0  # 与阶段17一致

N_Q = len(build_quarters())


def load_universes() -> dict[str, set[str]]:
    d = json.loads((ROOT / "data" / "stage18_index_universes.json").read_text(encoding="utf-8"))
    return {
        "csi985": set(d["000985"]["stocks"]),
        "hs300": set(d["000300"]["stocks"]),
        "csi_div": set(d["000922"]["stocks"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adjust", choices=("forward", "none"), default="forward")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default="data/stage18_results.json")
    args = ap.parse_args()

    root = resolve_hsjday_root()
    t0 = time.time()

    sse = load_index(root, INDEX_HS300)
    ords_all = np.array([d.toordinal() for d in sse.index], dtype=np.int64)
    lo, hi = PERIOD_START.toordinal(), PERIOD_END.toordinal()
    cal = ords_all[(ords_all >= lo) & (ords_all <= hi)]
    mkt = build_market_state(root, cal)
    r60 = mkt["r60"]
    ncal = len(cal)

    st15 = json.loads((ROOT / "data" / "stage15_analysis.json").read_text())
    base_avg = {h: np.array(st15["quarter_table_deep30"][str(h)]["base_avg_return"], dtype=float)
                for h in HOLDS}

    univ_sets = load_universes()
    univ_names = ["all", "csi985", "hs300", "csi_div"]

    symbols = list_stock_symbols(root, "hs")
    if args.limit:
        symbols = symbols[: args.limit]
    print("全市场 hs 个股 %d 只" % len(symbols))

    rules = ("deep30", "deep20")
    exc_sum = {u: {r: {h: np.zeros(N_Q) for h in HOLDS} for r in rules} for u in univ_names}
    exc_cnt = {u: {r: {h: np.zeros(N_Q) for h in HOLDS} for r in rules} for u in univ_names}
    wexc_sum = {u: {r: {h: np.zeros(N_Q) for h in HOLDS} for r in rules} for u in univ_names}
    wexc_cnt = {u: {r: {h: np.zeros(N_Q) for h in HOLDS} for r in rules} for u in univ_names}
    const_sum = {u: {h: np.zeros(N_Q) for h in HOLDS} for u in univ_names}
    const_cnt = {u: {h: np.zeros(N_Q) for h in HOLDS} for u in univ_names}
    mae_sum = {u: {r: {h: 0.0 for h in HOLDS} for r in rules} for u in univ_names}
    mfe_sum = {u: {r: {h: 0.0 for h in HOLDS} for r in rules} for u in univ_names}
    sig_cnt = {u: {r: {h: 0 for h in HOLDS} for r in rules} for u in univ_names}
    fsig_cnt = {u: {r: {h: 0 for h in HOLDS} for r in rules} for u in univ_names}

    n_scan = 0
    for i, code in enumerate(symbols):
        try:
            df = parse_day_file(resolve_symbol_path(root, code))
        except FileNotFoundError:
            continue
        n = len(df)
        if n < MIN_HIST_BARS + 1:
            continue
        if args.adjust == "forward":
            df = forward_adjust_frame(df, code)
        s = pin30_series(df)
        close = s["close"]
        high = df["high"].astype(float).to_numpy()
        low = df["low"].astype(float).to_numpy()
        short = s["short"]
        long_ = s["long"]
        trend = s["trend"]

        ords = np.array([d.toordinal() for d in df["date"].to_numpy()], dtype=np.int64)
        i0 = int(np.searchsorted(ords, PERIOD_START.toordinal(), side="left"))
        i1 = int(np.searchsorted(ords, PERIOD_END.toordinal(), side="right"))
        i0 = max(i0, MIN_HIST_BARS)
        if i1 - i0 < 1:
            continue
        n_scan += 1

        # 预计算 forward / mae / mfe 全序列（pandas rolling，与阶段17同口径）
        close_s = pd.Series(close)
        low_s = pd.Series(low)
        high_s = pd.Series(high)
        fwd = {h: (close_s.shift(-h) / close_s - 1.0).to_numpy(dtype=float) for h in HOLDS}
        mae = {h: (low_s.rolling(h, min_periods=h).min().shift(-h) / close_s - 1.0).to_numpy(dtype=float)
               for h in HOLDS}
        mfe = {h: (high_s.rolling(h, min_periods=h).max().shift(-h) / close_s - 1.0).to_numpy(dtype=float)
               for h in HOLDS}

        idx = np.arange(i0, i1, dtype=np.int64)
        ords_p = ords[i0:i1]
        qid = quarter_ids(ords_p)

        not_trend = ~trend[idx]
        m30 = not_trend & (short[idx] <= SHORT_PIN) & (long_[idx] <= LONG_DEEP_MAX)
        m20 = not_trend & (short[idx] <= SHORT_PIN20) & (long_[idx] <= LONG_DEEP_MAX)
        masks = {"deep30": m30, "deep20": m20}

        in_u = {"all"}
        if code in univ_sets["csi985"]:
            in_u.add("csi985")
        if code in univ_sets["hs300"]:
            in_u.add("hs300")
        if code in univ_sets["csi_div"]:
            in_u.add("csi_div")

        pos = np.searchsorted(cal, ords_p, side="left")
        pos_c = np.clip(pos, 0, ncal - 1)
        inb = (pos >= 0) & (pos < ncal) & (cal[pos_c] == ords_p)
        r60_at = np.full(len(ords_p), np.nan)
        r60_at[inb] = r60[pos_c[inb]]
        weak = ~np.isnan(r60_at) & (r60_at <= 0.0)

        # 本宇宙基线：全部交易日 forward return 按季度累加
        qsum = {h: np.zeros(N_Q) for h in HOLDS}
        qcnt = {h: np.zeros(N_Q) for h in HOLDS}
        for h in HOLDS:
            r = fwd[h][idx]
            v = ~np.isnan(r)
            np.add.at(qsum[h], qid[v], r[v])
            np.add.at(qcnt[h], qid[v], 1.0)
        for u in in_u:
            for h in HOLDS:
                const_sum[u][h] += qsum[h]
                const_cnt[u][h] += qcnt[h]

        # 信号：超额 + MAE/MFE
        for rule, m in masks.items():
            if not m.any():
                continue
            si = idx[m]
            si_qid = qid[m]
            si_weak = weak[m]
            for h in HOLDS:
                exc = fwd[h][si] - base_avg[h][si_qid]
                valid = ~np.isnan(exc)
                v_mae = mae[h][si]
                v_mfe = mfe[h][si]
                for u in in_u:
                    e = exc[valid]
                    q = si_qid[valid]
                    np.add.at(exc_sum[u][rule][h], q, e)
                    np.add.at(exc_cnt[u][rule][h], q, 1.0)
                    wm = valid & si_weak
                    we = exc[wm]
                    wq = si_qid[wm]
                    np.add.at(wexc_sum[u][rule][h], wq, we)
                    np.add.at(wexc_cnt[u][rule][h], wq, 1.0)
                    mae_sum[u][rule][h] += float(np.nansum(v_mae))
                    mfe_sum[u][rule][h] += float(np.nansum(v_mfe))
                    sig_cnt[u][rule][h] += int(valid.sum())
                    fsig_cnt[u][rule][h] += int((valid & si_weak).sum())

        if (i + 1) % 1000 == 0:
            print("  ...%d/%d 只扫描，%.0fs" % (i + 1, len(symbols), time.time() - t0), flush=True)

    results = {"meta": {"period": [str(PERIOD_START), str(PERIOD_END)],
                        "n_scanned": n_scan,
                        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")},
               "universes": {}}

    for u in univ_names:
        ures = {"rules": {}}
        for rule in rules:
            rres = {"holds": {}}
            for h in HOLDS:
                cbase = np.where(const_cnt[u][h] > 0, const_sum[u][h] / const_cnt[u][h], np.nan)
                esum = exc_sum[u][rule][h]
                ecnt = exc_cnt[u][rule][h]
                qexc = np.where(ecnt > 0, esum / ecnt, np.nan)
                pos_q = int(np.sum(qexc > 0))
                n_q = int(np.sum(~np.isnan(qexc)))
                qexc2 = np.where(ecnt > 0, esum / ecnt - cbase, np.nan)
                pos_q2 = int(np.sum(qexc2 > 0))
                n_q2 = int(np.sum(~np.isnan(qexc2)))
                wesum = wexc_sum[u][rule][h]
                wecnt = wexc_cnt[u][rule][h]
                wqexc = np.where(wecnt > 0, wesum / wecnt, np.nan)
                wpos = int(np.sum(wqexc > 0))
                wn = int(np.sum(~np.isnan(wqexc)))
                rres["holds"][h] = {
                    "n_signals": sig_cnt[u][rule][h],
                    "n_signals_weak": fsig_cnt[u][rule][h],
                    "excess_vs_market": {
                        "quarters": [None if np.isnan(x) else round(float(x) * 100, 3) for x in qexc],
                        "pos_q": pos_q, "n_q": n_q,
                        "p": None if n_q < 3 else binom_two_sided(pos_q, n_q),
                        "mean": None if n_q == 0 else round(float(np.nanmean(qexc)) * 100, 3),
                    },
                    "excess_vs_universe": {
                        "quarters": [None if np.isnan(x) else round(float(x) * 100, 3) for x in qexc2],
                        "pos_q": pos_q2, "n_q": n_q2,
                        "p": None if n_q2 < 3 else binom_two_sided(pos_q2, n_q2),
                        "mean": None if n_q2 == 0 else round(float(np.nanmean(qexc2)) * 100, 3),
                    },
                    "excess_weak": {
                        "quarters": [None if np.isnan(x) else round(float(x) * 100, 3) for x in wqexc],
                        "pos_q": wpos, "n_q": wn,
                        "p": None if wn < 3 else binom_two_sided(wpos, wn),
                        "mean": None if wn == 0 else round(float(np.nanmean(wqexc)) * 100, 3),
                    },
                    "mae": None if sig_cnt[u][rule][h] == 0 else round(mae_sum[u][rule][h] / sig_cnt[u][rule][h] * 100, 3),
                    "mfe": None if sig_cnt[u][rule][h] == 0 else round(mfe_sum[u][rule][h] / sig_cnt[u][rule][h] * 100, 3),
                }
            ures["rules"][rule] = rres
        results["universes"][u] = ures

    (ROOT / args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n落盘 %s（%.0fs）" % (ROOT / args.out, time.time() - t0))


if __name__ == "__main__":
    main()
