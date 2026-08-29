#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段15 追加分析：深水单针 vs 原始单针的环境互补性 + 环境切换规则可执行性检验。

只读 data/stage15_analysis.json（不重跑扫描）。产出 data/stage15_regime_switch.json。

三个问题：
1. 两条规则的季度超额是否负相关（互补）？
2. 「上涨季度用原始、其他季度用深水」的切换规则效果如何？（同期分档 = 有前视）
3. 把分档信号换成**滞后一季**（季初可知，可执行）后还成立吗？
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "stage15_analysis.json"
OUT = ROOT / "data" / "stage15_regime_switch.json"
MIN_N = 100
LAG_THRESHOLD = 0.03  # 上一季沪深300 涨幅 > 3% 视为「强势季」（≈ 同期上档 1/3 的下边界 +3.48%）


def binom_two_sided(k: int, n: int, p: float = 0.5) -> float:
    if n <= 0:
        return float("nan")
    pmf = lambda i: math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
    obs = pmf(k)
    return min(1.0, sum(pmf(i) for i in range(n + 1) if pmf(i) <= obs + 1e-15))


def pearson(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    xm, ym = x - x.mean(), y - y.mean()
    den = math.sqrt(float((xm ** 2).sum()) * float((ym ** 2).sum()))
    return float((xm * ym).sum() / den) if den else float("nan")


def rank(a):
    a = np.asarray(a, float); o = np.argsort(a)
    r = np.empty(len(a), float); r[o] = np.arange(1, len(a) + 1)
    return r


def spearman(x, y):
    return pearson(rank(x), rank(y))


def blk(vals) -> dict:
    v = np.asarray([x for x in vals if x is not None and np.isfinite(x)], float)
    n = len(v); k = int((v > 0).sum())
    return {"n_quarters": n, "n_positive": k,
            "p_binom_two_sided": round(binom_two_sided(k, n), 6),
            "mean": round(float(v.mean()), 6), "median": round(float(np.median(v)), 6),
            "min": round(float(v.min()), 6), "max": round(float(v.max()), 6),
            "sum": round(float(v.sum()), 6)}


def main() -> None:
    d = json.loads(SRC.read_text())
    L = d["meta"]["forward"]["quarters"]
    env = np.array([np.nan if x is None else x for x in d["env_hs300"]["ret"]], float)
    out: dict = {"meta": {"source": SRC.name, "min_n_quarter": MIN_N,
                          "lag_threshold": LAG_THRESHOLD,
                          "note": "switch_lookahead 用同期季度涨跌分档（有前视，仅诊断用）；"
                                  "switch_lagged 用上一季涨幅>3%（季初可知，可执行）"}}

    for h in ("20", "25", "60"):
        td, to = d["quarter_table_deep30"][h], d["quarter_table_orig"][h]
        ed = np.array([np.nan if x is None else x for x in td["excess_return"]], float)
        eo = np.array([np.nan if x is None else x for x in to["excess_return"]], float)
        nd = np.array(td["n"], float)
        keep = np.isfinite(ed) & (nd >= MIN_N) & np.isfinite(env)
        idx = np.where(keep)[0]
        top = set(idx[np.argsort(env[idx])][-((len(idx) + 2) // 3):].tolist()) \
            if len(idx) else set()
        top = set(np.array_split(idx[np.argsort(env[idx])], 3)[2].tolist())

        A, B, picks = [], [], []
        for i in range(len(L)):
            va = eo[i] if (i in top and np.isfinite(eo[i])) else ed[i]
            A.append(va)
            prev = env[i - 1] if i > 0 else np.nan
            use_orig = bool(np.isfinite(prev) and prev > LAG_THRESHOLD)
            vb = eo[i] if (use_orig and np.isfinite(eo[i])) else ed[i]
            B.append(vb)
            picks.append("orig" if use_orig else "deep30")

        k = np.isfinite(ed) & np.isfinite(eo)
        k2 = k.copy()
        k2[L.index("2026Q3")] = False  # orig 2026Q3 只有 120 个信号，超额 -23.6% 是极端值
        up = env > 0
        sw_sign = np.where(up & np.isfinite(eo), eo, ed)

        out[h] = {
            "always_deep30": blk(ed),
            "always_orig": blk(eo),
            "switch_lookahead_tercile": blk(A),
            "switch_lookahead_sign": blk(sw_sign),
            "switch_lagged_prev_quarter": blk(B),
            "lagged_picks": {L[i]: picks[i] for i in range(len(L))},
            "top_tercile_quarters": [L[i] for i in sorted(top)],
            "corr_deep30_vs_orig": {
                "pearson": round(pearson(ed[k], eo[k]), 4),
                "spearman": round(spearman(ed[k], eo[k]), 4),
                "n": int(k.sum()),
                "pearson_ex_2026Q3": round(pearson(ed[k2], eo[k2]), 4),
            },
            "by_index_sign": {
                "orig_up": blk(eo[np.isfinite(eo) & up]),
                "orig_down": blk(eo[np.isfinite(eo) & ~up]),
                "deep30_up": blk(ed[np.isfinite(ed) & up]),
                "deep30_down": blk(ed[np.isfinite(ed) & ~up]),
            },
        }
        print("=== hold %s 日 ===" % h)
        for key in ("always_deep30", "always_orig", "switch_lookahead_tercile",
                    "switch_lookahead_sign", "switch_lagged_prev_quarter"):
            v = out[h][key]
            print("  %-26s %2d/%-2d p=%-9s mean %+0.4f  median %+0.4f  sum %+0.4f" % (
                key, v["n_positive"], v["n_quarters"], v["p_binom_two_sided"],
                v["mean"], v["median"], v["sum"]))
        c = out[h]["corr_deep30_vs_orig"]
        print("  corr(deep30, orig) Pearson %+.3f / Spearman %+.3f (剔除2026Q3 %+.3f)" % (
            c["pearson"], c["spearman"], c["pearson_ex_2026Q3"]))
        print()

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("写出 %s" % OUT)


if __name__ == "__main__":
    main()
