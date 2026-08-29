#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 18 附带检查：调仓月（6/12月）后的 7月/1月 是否该空仓。

Jeremy 的问题：基金 6/12 月调仓，7月/1月空仓、8月/2月再做，胜率会不会更高。

方法：用阶段16 已缓存的 deep30 信号（全市场，含每条信号日期+前向收益），
按日历月切分 + 按月排除，重做 27 季度符号检验（减全市场基线，弱市 dir60↓ 过滤）。

不重扫，纯缓存分析。
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

from datasource.tdx.reader import resolve_hsjday_root, parse_day_file

PERIOD_START = date(2020, 1, 1)
PERIOD_END = date(2026, 8, 28)
HOLDS = (20, 25, 60)
INDEX_HS300 = "sh000300"


def binom_two_sided(k: int, n: int, p: float = 0.5) -> float:
    import math
    if n <= 0:
        return float("nan")
    pmf = lambda i: math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
    obs = pmf(k)
    return min(1.0, sum(pmf(i) for i in range(n + 1) if pmf(i) <= obs + 1e-15))


def build_r60(root: Path) -> tuple[np.ndarray, np.ndarray]:
    m, code = INDEX_HS300[:2], INDEX_HS300[2:]
    df = parse_day_file(root / m / "lday" / ("%s.day" % INDEX_HS300))
    hs = df.set_index("date")["close"].astype(float)
    lo, hi = PERIOD_START.toordinal(), PERIOD_END.toordinal()
    cal = np.array([d.toordinal() for d in hs.index if lo <= d.toordinal() <= hi], dtype=np.int64)
    cal_dates = [date.fromordinal(int(o)) for o in cal]
    close = hs.reindex(cal_dates).ffill().to_numpy(dtype=float)
    n = len(cal)
    r60 = np.full(n, np.nan)
    for i in range(n):
        if i >= 60:
            r60[i] = close[i] / close[i - 60] - 1.0
    return cal, r60


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/stage18_month_check.json")
    args = ap.parse_args()

    root = resolve_hsjday_root()
    cache = json.loads((ROOT / "data" / "stage16_signals_cache.json").read_text())
    sigs = cache["signals"]["deep30"]
    dates = np.asarray(sigs["date"], dtype=np.int64)
    qid = np.asarray(sigs["qid"], dtype=np.int64)

    st15 = json.loads((ROOT / "data" / "stage15_analysis.json").read_text())
    base_avg = {h: np.array(st15["quarter_table_deep30"][str(h)]["base_avg_return"], dtype=float)
                for h in HOLDS}

    cal, r60 = build_r60(root)
    # 信号日 → 日历下标 → r60
    pos = np.searchsorted(cal, dates, side="left")
    pos_c = np.clip(pos, 0, len(cal) - 1)
    inb = (pos >= 0) & (pos < len(cal)) & (cal[pos_c] == dates)
    r60_at = np.full(len(dates), np.nan)
    r60_at[inb] = r60[pos_c[inb]]

    months = np.array([date.fromordinal(int(d)).month for d in dates], dtype=np.int16)

    out = {"meta": {"period": [str(PERIOD_START), str(PERIOD_END)],
                    "n_signals": int(len(dates)),
                    "generated_at": pd.Timestamp.now().isoformat()},
           "by_month": {}, "exclusions": {}}

    # ---- 逐月描述（dir60↓ 过滤后，25日主口径） ----
    h = 25
    filt = (~np.isnan(r60_at)) & (r60_at <= 0.0)
    ret = np.asarray(sigs["ret%d" % h], dtype=float)
    exc = ret - base_avg[h][qid]
    valid = filt & ~np.isnan(exc)

    by_month = {}
    for mo in range(1, 13):
        m = valid & (months == mo)
        if m.sum() == 0:
            by_month[mo] = {"n": 0, "mean_excess": None}
            continue
        by_month[mo] = {"n": int(m.sum()),
                        "mean_excess": round(float(np.nanmean(exc[m])) * 100, 3),
                        "mean_ret": round(float(np.nanmean(ret[m])) * 100, 3)}
    out["by_month"] = by_month

    # ---- 排除方案：重做 27 季度符号检验 ----
    def sign_test(mask) -> dict:
        qs = np.unique(qid[mask & ~np.isnan(exc)])
        exc_m = exc[mask]
        qid_m = qid[mask]
        per_q = [np.nanmean(exc_m[qid_m == q]) for q in sorted(qs)]
        pos = sum(1 for x in per_q if x > 0)
        return {"n_q": int(len(per_q)), "pos_q": pos,
                "p": None if len(per_q) < 3 else binom_two_sided(pos, len(per_q)),
                "mean_excess": round(float(np.mean(per_q)) * 100, 3),
                "quarters": [round(x * 100, 3) for x in per_q]}

    schemes = {
        "all_months": valid,
        "excl_Jul_Jan": valid & ~np.isin(months, [7, 1]),
        "excl_Jun_Dec": valid & ~np.isin(months, [6, 12]),
        "only_Aug_Feb": valid & np.isin(months, [8, 2]),
        "excl_JunJul_DecJan": valid & ~np.isin(months, [6, 7, 12, 1]),
    }
    for name, mask in schemes.items():
        out["exclusions"][name] = {"n": int(mask.sum()), **sign_test(mask)}

    (ROOT / args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== 逐月（deep30, 25日, dir60↓, 减全市场基线）===")
    for mo in range(1, 13):
        r = by_month[mo]
        if r["mean_excess"] is None:
            print("  %2d月  n=0" % mo)
        else:
            print("  %2d月  n=%6d  mean_excess=%+.3f%%  mean_ret=%+.3f%%" %
                  (mo, r["n"], r["mean_excess"], r["mean_ret"]))
    print("\n=== 排除方案（27季度符号检验，25日）===")
    for name, r in out["exclusions"].items():
        print("  %-22s n=%7d  %d/%d 正 (p=%s)  均值超额 %+.3f%%" %
              (name, r["n"], r["pos_q"], r["n_q"], r["p"], r["mean_excess"]))
    print("\n落盘", ROOT / args.out)


if __name__ == "__main__":
    main()
