#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段15 追加分析：原始单针（orig）在不同市场环境季度的表现。

动机：深水单针在「涨得最多的 1/3 季度」0/9 为正（逆势工具）。反问——原始单针
（趋势多头 + 长期随机 >= 80）在这 9 个上涨季度里是不是正的？若是，两者按环境互补。

只读 data/stage15_analysis.json，不重跑扫描。分档口径与 analyze_stage15.py 完全一致：
按沪深300 季度涨跌幅升序 np.array_split(order, 3)，keep = 有限值 & n>=100。
主结果用**深水单针的同一批季度名单**（同 9 个季度，apples-to-apples）。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "stage15_analysis.json"
OUT = ROOT / "data" / "stage15_orig_regime.json"
MIN_N = 100


def binom_two_sided(k: int, n: int, p: float = 0.5) -> float:
    if n <= 0:
        return float("nan")

    def pmf(i):
        return math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i))

    obs = pmf(k)
    tot = sum(pmf(i) for i in range(n + 1) if pmf(i) <= obs + 1e-15)
    return min(1.0, tot)


def pearson(x, y):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if len(x) < 3:
        return float("nan")
    xm, ym = x - x.mean(), y - y.mean()
    d = math.sqrt(float((xm ** 2).sum()) * float((ym ** 2).sum()))
    return float((xm * ym).sum() / d) if d else float("nan")


def rank(a):
    a = np.asarray(a, float)
    order = np.argsort(a)
    r = np.empty(len(a), float)
    r[order] = np.arange(1, len(a) + 1)
    return r


def spearman(x, y):
    return pearson(rank(x), rank(y))


def stat_block(vals) -> dict:
    v = np.asarray([x for x in vals if x is not None and np.isfinite(x)], float)
    n = len(v)
    k = int((v > 0).sum())
    return {
        "n_quarters": n,
        "n_positive": k,
        "share_positive": round(k / n, 4) if n else None,
        "p_binom_two_sided": round(binom_two_sided(k, n), 6) if n else None,
        "mean": round(float(v.mean()), 6) if n else None,
        "median": round(float(np.median(v)), 6) if n else None,
        "min": round(float(v.min()), 6) if n else None,
        "max": round(float(v.max()), 6) if n else None,
        "sum": round(float(v.sum()), 6) if n else None,
    }


def main() -> None:
    d = json.loads(SRC.read_text())
    labels = d["meta"]["forward"]["quarters"]
    env_ret = np.array([np.nan if x is None else x for x in d["env_hs300"]["ret"]], float)
    out: dict = {"meta": {"source": SRC.name, "min_n_quarter": MIN_N,
                          "bucket_rule": "沪深300季度涨跌幅升序 array_split(3)，与 analyze_stage15.py 一致"}}

    for h in ("20", "25", "60"):
        td = d["quarter_table_deep30"][h]
        to = d["quarter_table_orig"][h]
        ed = np.array([np.nan if x is None else x for x in td["excess_return"]], float)
        eo = np.array([np.nan if x is None else x for x in to["excess_return"]], float)
        wo = np.array([np.nan if x is None else x for x in to["excess_win_rate"]], float)
        nd = np.array(td["n"], float)
        no = np.array(to["n"], float)

        # 深水单针的分档（主口径，用于对齐同一批季度）
        keep_d = np.isfinite(ed) & (nd >= MIN_N) & np.isfinite(env_ret)
        idx_d = np.where(keep_d)[0]
        order = idx_d[np.argsort(env_ret[idx_d])]
        buckets = np.array_split(order, 3)
        names = ["跌得最多的1/3", "中间1/3", "涨得最多的1/3"]

        print("=" * 118)
        print("持有 %s 日 —— 按沪深300季度涨跌幅三分档（档位名单沿用深水单针口径）" % h)
        print("=" * 118)
        print("  %-14s %-9s %-11s %-11s %-11s %-11s" % (
            "档位", "季度数", "深水超额", "原始超额", "原始超额胜率", "原始正/总"))
        for nm, sel in zip(names, buckets):
            selo = [i for i in sel if np.isfinite(eo[i]) and no[i] >= MIN_N]
            bd = stat_block(ed[sel])
            bo = stat_block(eo[selo]) if selo else None
            bw = stat_block(wo[selo]) if selo else None
            print("  %-14s %-9d %+10.4f %+10s %+12s %10s" % (
                nm, len(sel), bd["mean"],
                ("%.4f" % bo["mean"]) if bo else "n/a",
                ("%.4f" % bw["mean"]) if bw else "n/a",
                ("%d/%d" % (bo["n_positive"], bo["n_quarters"])) if bo else "n/a"))
            out["%s|档|%s" % (h, nm)] = {
                "quarters": [labels[i] for i in sel],
                "deep30_excess_return": bd,
                "orig_excess_return": bo,
                "orig_excess_win_rate": bw,
                "orig_quarters_used": [labels[i] for i in selo],
                "orig_per_quarter": {labels[i]: {
                    "n": int(no[i]) if np.isfinite(no[i]) else None,
                    "excess_return": None if not np.isfinite(eo[i]) else round(float(eo[i]), 6),
                    "excess_win_rate": None if not np.isfinite(wo[i]) else round(float(wo[i]), 6),
                    "hs300_ret": None if not np.isfinite(env_ret[i]) else round(float(env_ret[i]), 6),
                } for i in sel},
            }

        # 原始单针自己的相关性
        keep_o = np.isfinite(eo) & (no >= MIN_N) & np.isfinite(env_ret)
        if keep_o.sum() >= 3:
            pr = pearson(env_ret[keep_o], eo[keep_o])
            sp = spearman(env_ret[keep_o], eo[keep_o])
            prw = pearson(env_ret[keep_o], wo[keep_o])
            spw = spearman(env_ret[keep_o], wo[keep_o])
            out["%s|corr" % h] = {"excess_return": {"pearson": round(pr, 4), "spearman": round(sp, 4)},
                                  "excess_win_rate": {"pearson": round(prw, 4), "spearman": round(spw, 4)},
                                  "n": int(keep_o.sum())}
            print("  原始单针 超额收益 vs 沪深300涨跌幅  Pearson %+.3f  Spearman %+.3f  (n=%d)" % (
                pr, sp, int(keep_o.sum())))
            print("  原始单针 超额胜率 vs 沪深300涨跌幅  Pearson %+.3f  Spearman %+.3f" % (prw, spw))
        print()

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("写出 %s" % OUT)


if __name__ == "__main__":
    main()
