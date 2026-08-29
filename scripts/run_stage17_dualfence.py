#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 17 任务 5：双防线在 ETF 上重测（阶段 13/14 在个股上失效的那套）。

1. 进攻 K（阈值 4%）触发率 + 中点防线样本可用性。
2. 三条线（生命线 / 阴量定价线 / 进攻K中点）作为洗盘判别器：
   分「回踩不破=洗盘」vs「已破2日=破位」两组比前向收益，看在 ETF 上是否仍是负 alpha。

口径：与阶段 14 §3 一致（base 事件 = 深水单针 deep30；三条线序列复用 stage14 原语）。
宇宙：主口径 liq_50M_rho_0.95（dedup 后代表 ETF，剔除债券）。

用法：
    .venv/bin/python scripts/run_stage17_dualfence.py --out data/stage17_dualfence.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datasource.tdx.reader import parse_day_file, resolve_hsjday_root
from market.adjust import forward_adjust_frame
from indicators.stage13 import detect_attack_candles
from indicators.stage14 import (
    attack_defense_series, lifeline_series, line_broken_2day, yin_volume_line_series,
)
from scripts.pin30_common import pin30_series
from scripts.stage17_classify import EQUITY_GROUPS, classify_symbol, load_names

PANEL_START = date(2019, 1, 1)
PERIOD_START = date(2020, 1, 1)
PERIOD_END = date(2026, 8, 28)
HOLDS = (20, 25, 60)
MIN_HIST_BARS = 120
MAIN_COMBO = "liq_50M_rho_0.95"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/stage17_dualfence.json")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    root = resolve_hsjday_root()
    names = load_names()
    univ_json = json.loads((ROOT / "data" / "stage17_universe.json").read_text(encoding="utf-8"))
    reb = univ_json["combinations"][MAIN_COMBO]

    # master calendar
    sse = parse_day_file(root / "sh" / "lday" / "sh000001.day")
    ords = np.array([d.toordinal() for d in sse["date"].to_numpy()], dtype=np.int64)
    lo, hi = PANEL_START.toordinal(), PERIOD_END.toordinal()
    m = (ords >= lo) & (ords <= hi)
    cal_ord = ords[m]

    # ever_in 权益 ETF
    syms = sorted(s for s in reb["ever_in"] if classify_symbol(s, names)[0] in EQUITY_GROUPS)
    if args.limit:
        syms = syms[: args.limit]
    code2month = defaultdict(list)  # code -> list of month-index in universe
    rebalances = [(r["date"], [x["code"] for x in r["reps"]]) for r in reb["rebalances"]]
    rep_months = defaultdict(list)  # code -> [month_id]
    for mi, (d, reps) in enumerate(rebalances):
        for c in reps:
            rep_months[c].append(mi)
    reb_ord = np.array([date.fromisoformat(d).toordinal() for d, _ in rebalances], dtype=np.int64)
    reb_idx = np.searchsorted(cal_ord, reb_ord, side="left")
    n_days = len(cal_ord)
    day_month = np.zeros(n_days, dtype=np.int32)
    for mi in range(len(reb_idx)):
        s = reb_idx[mi]
        e = reb_idx[mi + 1] if mi + 1 < len(reb_idx) else n_days
        day_month[s:e] = mi

    # 统计累加
    atk_days = 0
    tot_days = 0
    atk_etfs_with = 0
    etfs_counted = 0
    # 三条线判别器：line -> hold -> {A_ret[], B_ret[]}
    disc = {ln: {h: {"A": [], "B": [], "A_n": 0, "B_n": 0} for h in HOLDS}
            for ln in ("lifeline", "yinvol", "attack")}
    # 进攻K中点防线样本可用性（deep30 信号日有活跃防线）
    deep30_n = 0
    deep30_with_atk = 0

    t0 = time.time()
    for j, sym in enumerate(syms):
        m_, code = sym[:2], sym[2:]
        try:
            df = parse_day_file(root / m_ / "lday" / ("%s.day" % sym))
        except FileNotFoundError:
            continue
        if df.empty:
            continue
        df = forward_adjust_frame(df, sym)
        closes = df["close"].astype(float).to_numpy()
        highs = df["high"].astype(float).to_numpy()
        lows = df["low"].astype(float).to_numpy()
        opens = df["open"].astype(float).to_numpy()
        vols = df["volume"].astype(float).to_numpy()
        own_ord = np.array([d.toordinal() for d in df["date"].to_numpy()], dtype=np.int64)
        n = len(df)
        if n < MIN_HIST_BARS + 1:
            continue

        s = pin30_series(df)
        short = s["short"]
        long_ = s["long"]
        trend = s["trend"]

        # 进攻 K（etf 阈值 4%）
        atk = detect_attack_candles(opens.tolist(), closes.tolist(), "etf")
        etfs_counted += 1
        if atk:
            atk_etfs_with += 1
        # 触发率按「周期内交易日」算
        i0 = int(np.searchsorted(own_ord, PERIOD_START.toordinal(), side="left"))
        i1 = int(np.searchsorted(own_ord, PERIOD_END.toordinal(), side="right"))
        atk_days += sum(1 for a in atk if i0 <= a < i1)
        tot_days += max(0, i1 - i0)

        # deep30 信号
        idx = np.arange(max(i0, MIN_HIST_BARS), i1, dtype=np.int64)
        deep30 = (~trend[idx]) & (short[idx] <= 30.0) & (long_[idx] <= 55.0)
        si = idx[deep30]
        if si.size == 0:
            continue

        # 三条线序列
        ll = lifeline_series(highs.tolist(), lows.tolist(), closes.tolist())
        yv = yin_volume_line_series(highs.tolist(), lows.tolist(), opens.tolist(),
                                    closes.tolist(), vols.tolist())
        ad = attack_defense_series(opens.tolist(), highs.tolist(), lows.tolist(),
                                   closes.tolist(), "etf")
        ll = np.asarray(ll, dtype=float)
        yv = np.asarray(yv, dtype=float)
        ad = np.asarray(ad, dtype=float)

        # 信号日所属月份 + 是否在宇宙内
        sig_cal = np.searchsorted(cal_ord, own_ord[si], side="left")
        sig_cal = np.clip(sig_cal, 0, n_days - 1)
        months = rep_months.get(sym, [])
        ms = set(months)
        in_u = np.array([day_month[c] in ms for c in sig_cal], dtype=bool)

        for line, series in (("lifeline", ll), ("yinvol", yv), ("attack", ad)):
            # 前向收益
            for h in HOLDS:
                ok = (si + h) < n
                for k in range(si.size):
                    t = si[k]
                    if not in_u[k] or not ok[k]:
                        continue
                    lv = series[t]
                    if not np.isfinite(lv):
                        continue
                    fwd = closes[t + h] / closes[t] - 1.0
                    broken2 = line_broken_2day(closes.tolist(), float(lv), int(t))
                    if closes[t] >= lv:
                        disc[line][h]["A"].append(fwd)
                        disc[line][h]["A_n"] += 1
                    elif broken2:
                        disc[line][h]["B"].append(fwd)
                        disc[line][h]["B_n"] += 1
                    # 单日破（灰区）不归入任一组

        # 进攻K中点防线可用性（deep30 且 in_u 且 attack 防线有效）
        for k in range(si.size):
            t = si[k]
            if not in_u[k]:
                continue
            deep30_n += 1
            if np.isfinite(ad[t]):
                deep30_with_atk += 1

        if (j + 1) % 200 == 0:
            print("  ...%d/%d 只，%.1fs" % (j + 1, len(syms), time.time() - t0), flush=True)

    # 汇总
    result = {
        "meta": {"main_combo": MAIN_COMBO, "n_etf": len(syms),
                 "period": [str(PERIOD_START), str(PERIOD_END)],
                 "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")},
        "attack_trigger": {
            "etfs_counted": etfs_counted,
            "etfs_with_attack": atk_etfs_with,
            "etf_share_with_attack": round(atk_etfs_with / etfs_counted, 6) if etfs_counted else None,
            "attack_days": atk_days,
            "total_days": tot_days,
            "day_trigger_rate": round(atk_days / tot_days, 6) if tot_days else None,
        },
        "attack_midpoint_availability": {
            "deep30_signals_in_universe": deep30_n,
            "deep30_with_active_attack_line": deep30_with_atk,
            "share": round(deep30_with_atk / deep30_n, 6) if deep30_n else None,
        },
        "discriminator": {},
    }
    for line in ("lifeline", "yinvol", "attack"):
        result["discriminator"][line] = {}
        for h in HOLDS:
            d = disc[line][h]
            A = np.array(d["A"], dtype=float)
            B = np.array(d["B"], dtype=float)
            a_mean = float(A.mean()) if A.size else None
            b_mean = float(B.mean()) if B.size else None
            result["discriminator"][line][str(h)] = {
                "A_n": d["A_n"], "B_n": d["B_n"],
                "A_ret_mean": round(a_mean, 6) if a_mean is not None else None,
                "B_ret_mean": round(b_mean, 6) if b_mean is not None else None,
                "delta_A_minus_B": round((a_mean - b_mean), 6)
                if (a_mean is not None and b_mean is not None) else None,
            }

    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n已写出 %s，总耗时 %.1fs" % (args.out, time.time() - t0))


if __name__ == "__main__":
    main()
