#!/usr/bin/env python3
"""阶段 11 第 2 段：敏感性附录（复用 run_regime_basket_backtest 落盘的 npz）。

两个自由参数稳健性：
  1. 资金流入篮子 top-N ∈ {3, 5, 8}
  2. regime 阈值 ±2%（主口径） vs ±3%（任务书原列最宽松档）

不改主口径结论，只验证「大跌防御跑输 / 大涨进攻跑输」是否由参数选择造成。

用法（仓库根目录）：
    .venv/bin/python scripts/run_regime_basket_sensitivity.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HSJDAY = Path.home() / "Desktop" / "每日复盘" / "hsjday"
OUT = DATA / "regime_basket_sensitivity.json"

LOOKBACK = 20
HORIZONS = (20, 60)
WINDOWS = [
    ("IS", "2026-03-01", "2026-08-27"),
    ("OOS-A", "2023-01-01", "2023-12-31"),
    ("OOS-B", "2024-01-01", "2024-12-31"),
    ("OOS-C", "2025-01-01", "2026-02-28"),
]
OOS_LABELS = ["OOS-A", "OOS-B", "OOS-C"]


def main() -> None:
    z = np.load(DATA / "regime_basket_arrays.npz", allow_pickle=False)
    index_dates = z["index_dates"].astype(np.int64)
    regime2 = z["regime"].astype(str)
    mret = z["mret"]; midx = z["midx"]
    bret = z["bret"]; bidx = z["bidx"]
    sector_codes = [str(c) for c in z["sector_codes"]]
    sret = z["sret"]; sidx = z["sidx"]; sr20 = z["sr20"]; share_chg = z["share_chg"]
    mr20 = z["mr20"]
    N_DAYS = len(index_dates)

    def classify2(r, up, down):
        if r >= up: return "大涨"
        if r <= down: return "大跌"
        return "中性"

    # 重新算 r20（上证指数）供阈值敏感性
    raw = (HSJDAY / "sh" / "lday" / "sh000001.day").read_bytes()
    n = len(raw) // 32
    dt = np.dtype([("date", "<u4"), ("open", "<u4"), ("high", "<u4"), ("low", "<u4"),
                   ("close", "<u4"), ("amount", "<f4"), ("volume", "<u4"), ("res", "<u4")])
    arr = np.frombuffer(raw[: n * 32], dtype=dt)
    ad = arr["date"].astype(np.int64)
    ac = arr["close"].astype(np.float64) / 100.0
    lo, hi = 20221201, 20260827
    mask = (ad >= lo) & (ad <= hi)
    wd = ad[mask]; wc = ac[mask]
    r20_all = pd.Series(wc).pct_change(LOOKBACK).to_numpy()

    rel = sr20 - mr20[None, :]

    def top_at(pos, up, down, nn, chg_threshold=0.0):
        cand = []
        for k in range(len(sector_codes)):
            r = rel[k][pos]; ch = share_chg[k][pos]
            if np.isnan(r) or np.isnan(ch):
                continue
            if ch > chg_threshold:
                cand.append((r, k))
        cand.sort(key=lambda x: -x[0])
        return [k for _, k in cand[:nn]]

    def fwd(entry, h, lv):
        j = entry + h
        if j >= N_DAYS or lv[entry] <= 0:
            return np.nan
        return float(lv[j] / lv[entry] - 1.0)

    def period_pos(label):
        s, e = [w for w in WINDOWS if w[0] == label][0][1:]
        sd, ed = int(s.replace("-", "")), int(e.replace("-", ""))
        return [i for i, d in enumerate(index_dates) if sd <= d <= ed]

    def pooled_bucket_pos(labels, up, down, bucket):
        out = []
        for lb in labels:
            for i in period_pos(lb):
                if i < LOOKBACK:
                    continue
                if classify2(r20_all[i], up, down) == bucket:
                    out.append(i)
        return out

    def agg_excess(days, up, down, nn):
        """返回 {h: {defensive_excess_mean, aggressive_excess_mean, market_mean}}"""
        res = {}
        for h in HORIZONS:
            m_l, b_l, a_l = [], [], []
            for i in days:
                entry = i + 1
                if entry >= N_DAYS:
                    continue
                m = fwd(entry, h, midx)
                b = fwd(entry, h, bidx)
                if m == m:
                    m_l.append(m)
                if m == m and b == b:
                    b_l.append(b - m)
                ts = top_at(i, up, down, nn)
                if ts and m == m:
                    vals = [fwd(entry, h, sidx[k]) for k in ts]
                    vals = [v for v in vals if v == v]
                    if vals:
                        a_l.append(float(np.mean(vals)) - m)
            res[str(h)] = {
                "market_mean": round(float(np.mean(m_l)), 6) if m_l else None,
                "defensive_excess": round(float(np.mean(b_l)), 6) if b_l else None,
                "aggressive_excess": round(float(np.mean(a_l)), 6) if a_l else None,
                "n": int(len(m_l)),
            }
        return res

    result = {"n_sensitivity": {}, "threshold_sensitivity": {}}

    # 1) top-N 敏感性（主口径 ±2%）
    for nn in (3, 5, 8):
        result["n_sensitivity"][f"N={nn}"] = {
            "大涨": agg_excess(pooled_bucket_pos(OOS_LABELS, 0.02, -0.02, "大涨"), 0.02, -0.02, nn),
            "大跌": agg_excess(pooled_bucket_pos(OOS_LABELS, 0.02, -0.02, "大跌"), 0.02, -0.02, nn),
        }

    # 2) 阈值敏感性（N=5）：±3% 档
    for (up, down, tag) in ((0.02, -0.02, "+2%/-2%主口径"), (0.03, -0.03, "+3%/-3%")):
        result["threshold_sensitivity"][tag] = {
            "大跌": agg_excess(pooled_bucket_pos(OOS_LABELS, up, down, "大跌"), up, down, 5),
            "大涨": agg_excess(pooled_bucket_pos(OOS_LABELS, up, down, "大涨"), up, down, 5),
        }

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    # 打印
    print("== top-N 敏感性（OOS pooled，主口径 ±2%）==")
    for nn in (3, 5, 8):
        r = result["n_sensitivity"][f"N={nn}"]
        print(f"  N={nn}: 大涨 20d agg_exc={r['大涨']['20']['aggressive_excess']} | 大跌 20d def_exc={r['大跌']['20']['defensive_excess']}")
    print("\n== 阈值敏感性（OOS pooled，N=5）==")
    for tag in result["threshold_sensitivity"]:
        r = result["threshold_sensitivity"][tag]
        print(f"  {tag}: 大跌20d def_exc={r['大跌']['20']['defensive_excess']} n={r['大跌']['20']['n']} | 大涨20d agg_exc={r['大涨']['20']['aggressive_excess']} n={r['大涨']['20']['n']}")
    print(f"\n已落盘 {OUT}")


if __name__ == "__main__":
    main()
