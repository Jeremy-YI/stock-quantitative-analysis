#!/usr/bin/env python3
"""阶段 15 分析层：把 27 个季度的累加结果变成结论。

输入 = `scripts/run_stage15.py` 落盘的 JSON（前复权主口径 + 未复权对照）。
输出 = 控制台报表 + `data/stage15_analysis.json`。

## 四块分析

1. **27 个季度的独立结果**：每季度样本量 / 20-25-60 日超额胜率（减**同季度**基线）/
   超额收益与绝对收益**分列** / MAE / MFE。
   统计检验：**符号检验**（27 个季度里多少个超额为正，二项精确 p 值，H0: p=0.5），
   超额的均值 / 中位数 / 标准差 / 最好最差季度 / 正季度的集中度
   （前 3 个正季度贡献了多少比例的总超额——用来判断是不是靠个别行情撑起来的）。
2. **超额 vs 市场环境**：每季度打标（沪深300 / 上证的季度涨跌幅、振幅、最大回撤），
   算 Pearson + Spearman 相关，并按环境分档看超额。
3. **季报窗口效应**：信号落在披露窗口前 20 日 / 窗口内 / 窗口后 20 日 / 其他，
   四组的超额差异（每组减**同季度同组**基线，避免用季度整体基线混淆环境）。
4. **两个偏差**：幸存者偏差（每季度初有数据的股票数 vs 公开上市家数）、
   复权（前复权 vs 未复权的结论方向是否一致）。

统计实现自带（本机无 scipy）：二项精确检验用 math.comb，Spearman 用秩的 Pearson。

用法：
    .venv/bin/python scripts/analyze_stage15.py \
        --forward data/stage15_forward_hs.json --none data/stage15_none_hs.json \
        --forward-all data/stage15_forward_all.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datasource.tdx.reader import parse_day_file, resolve_hsjday_root

from scripts.run_stage15 import (
    EARN_GROUPS,
    EARN_NAMES,
    HOLDS,
    INDEX_HS300,
    INDEX_SSE,
    MIN_N_QUARTER,
    N_EG,
    N_Q,
    Q_LABELS,
    QUARTERS,
    RULE_NAMES,
    RULES,
    load_index_frame,
)

# 公开常识值：A 股（沪深两市）上市公司家数，用于幸存者偏差量化。
# 口径 = 沪深两市 A 股上市公司数（不含北交所），来源为交易所年度统计的常用引用值，
# **是近似值**，只用来估算「缺失比例」的量级，不做精确断言。
LISTED_REF_HS = {
    "2020Q1": 3760, "2021Q1": 4150, "2022Q1": 4610,
    "2023Q1": 4920, "2024Q1": 5110, "2025Q1": 5130, "2026Q1": 5170,
}
LISTED_REF_NOTE = (
    "沪深两市 A 股上市公司家数的公开近似值：2020 年初约 3760、2021 年初约 4150、"
    "2022 年初约 4610、2023 年初约 4920、2024 年初约 5110、2025 年初约 5130、2026 年初约 5170。"
)


# ---------------------------------------------------------------------------
# 统计工具（无 scipy）
# ---------------------------------------------------------------------------


def binom_test_two_sided(k: int, n: int, p: float = 0.5) -> float:
    """精确二项检验（双侧，等尾概率法）：H0 = 成功率 p。n<=27，直接枚举。"""
    if n == 0:
        return 1.0
    probs = [math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(n + 1)]
    obs = probs[k]
    tol = obs * (1 + 1e-9)
    return float(min(1.0, sum(pr for pr in probs if pr <= tol)))


def pearson(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3:
        return float("nan")
    xm, ym = x - x.mean(), y - y.mean()
    d = math.sqrt(float((xm**2).sum()) * float((ym**2).sum()))
    return float((xm * ym).sum() / d) if d > 0 else float("nan")


def rankdata(a: np.ndarray) -> np.ndarray:
    """平均秩（处理并列）。"""
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    sa = a[order]
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and sa[j + 1] == sa[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    return pearson(rankdata(x), rankdata(y))


# ---------------------------------------------------------------------------
# 累加器 → 季度指标
# ---------------------------------------------------------------------------


def cell_to_q(v: np.ndarray) -> np.ndarray:
    """(N_Q*N_EG,) → (N_Q,)（把季报窗口分组加总回季度）。"""
    return np.asarray(v, dtype=np.float64).reshape(N_Q, N_EG).sum(axis=1)


def cell_to_qe(v: np.ndarray) -> np.ndarray:
    """(N_Q*N_EG,) → (N_Q, N_EG)。"""
    return np.asarray(v, dtype=np.float64).reshape(N_Q, N_EG)


def safe_div(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    out = np.full_like(a, np.nan, dtype=np.float64)
    m = b > 0
    out[m] = a[m] / b[m]
    return out


def quarter_table(state: dict, rule: str, hold: int) -> dict:
    """算某规则某持有期的 27 个季度指标（含减同季度基线的超额）。"""
    r = state["rule"][rule][str(hold)]
    b = state["base"][str(hold)]
    n = cell_to_q(r["n"])
    win = cell_to_q(r["win"])
    sret = cell_to_q(r["sum_ret"])
    smae = cell_to_q(r["sum_mae"])
    smfe = cell_to_q(r["sum_mfe"])
    bn = cell_to_q(b["n"])
    bwin = cell_to_q(b["win"])
    bsret = cell_to_q(b["sum_ret"])

    wr = safe_div(win, n)
    ar = safe_div(sret, n)
    bwr = safe_div(bwin, bn)
    bar = safe_div(bsret, bn)
    return {
        "n": n,
        "win_rate": wr,
        "avg_return": ar,
        "base_n": bn,
        "base_win_rate": bwr,
        "base_avg_return": bar,
        "excess_win_rate": wr - bwr,
        "excess_return": ar - bar,
        "mae": safe_div(smae, n),
        "mfe": safe_div(smfe, n),
    }


def sign_test_block(vals: np.ndarray, n_arr: np.ndarray, min_n: int) -> dict:
    """对 27 个季度的超额序列做符号检验 + 分布统计。

    两套口径：全部季度 / 只算样本量 >= min_n 的季度（两者都报，不挑）。
    """
    out = {}
    for tag, keep in (("all", np.isfinite(vals)),
                      ("suff", np.isfinite(vals) & (n_arr >= min_n))):
        v = vals[keep]
        if v.size == 0:
            out[tag] = None
            continue
        pos = int((v > 0).sum())
        tot = int(v.size)
        # 集中度：正季度里最大的 3 个贡献了多少「正超额总量」
        posv = np.sort(v[v > 0])[::-1]
        top3 = float(posv[:3].sum())
        possum = float(posv.sum())
        out[tag] = {
            "n_quarters": tot,
            "n_positive": pos,
            "share_positive": round(pos / tot, 4),
            "p_binom_two_sided": round(binom_test_two_sided(pos, tot), 6),
            "mean": round(float(v.mean()), 6),
            "median": round(float(np.median(v)), 6),
            "std": round(float(v.std(ddof=1)), 6) if tot > 1 else None,
            "min": round(float(v.min()), 6),
            "max": round(float(v.max()), 6),
            "sum": round(float(v.sum()), 6),
            "top3_share_of_positive_sum": round(top3 / possum, 4) if possum > 0 else None,
            "top3_share_of_total_sum": round(top3 / float(v.sum()), 4) if abs(float(v.sum())) > 1e-12 else None,
        }
    return out


# ---------------------------------------------------------------------------
# 市场环境
# ---------------------------------------------------------------------------


def index_quarter_env(code: str) -> dict:
    """每季度的指数环境：涨跌幅 / 振幅 / 季内最大回撤（收盘口径）。"""
    root = resolve_hsjday_root()
    df = load_index_frame(root, code)
    ords = np.array([d.toordinal() for d in df["date"]], dtype=np.int64)
    close = df["close"].astype(float).to_numpy()
    high = df["high"].astype(float).to_numpy()
    low = df["low"].astype(float).to_numpy()

    ret = np.full(N_Q, np.nan)
    amp = np.full(N_Q, np.nan)
    mdd = np.full(N_Q, np.nan)
    for qi, q in enumerate(QUARTERS):
        i0 = int(np.searchsorted(ords, q["start"].toordinal(), side="left"))
        i1 = int(np.searchsorted(ords, q["end"].toordinal(), side="right"))
        if i1 - i0 < 2:
            continue
        prev = close[i0 - 1] if i0 > 0 else close[i0]
        seg_c = close[i0:i1]
        ret[qi] = seg_c[-1] / prev - 1.0
        amp[qi] = (high[i0:i1].max() - low[i0:i1].min()) / prev
        run = np.maximum.accumulate(np.concatenate(([prev], seg_c)))
        mdd[qi] = float((np.concatenate(([prev], seg_c)) / run - 1.0).min())
    return {"ret": ret, "amp": amp, "mdd": mdd}


# ---------------------------------------------------------------------------
# 报表
# ---------------------------------------------------------------------------


def fmt(v: float, scale: float = 100.0, nd: int = 2, sign: bool = True) -> str:
    if v is None or not np.isfinite(v):
        return "  n/a"
    f = "%+.*f" if sign else "%.*f"
    return f % (nd, v * scale)


def print_quarter_tables(state: dict, title: str) -> dict:
    print("\n" + "=" * 132)
    print("【%s】27 个季度独立结果 —— 深水单针 短<=30（超额 = 减同季度全市场个股等权基线）" % title)
    print("=" * 132)
    tabs = {h: quarter_table(state, "deep30", h) for h in HOLDS}
    print("%-8s %8s | %s" % ("季度", "信号n",
          " | ".join("%d日 超胜pp/超收%%/绝收%%/基线%%/MAE/MFE" % h for h in HOLDS)))
    print("-" * 132)
    for qi, lab in enumerate(Q_LABELS):
        row = "%-8s %8d |" % (lab, tabs[HOLDS[0]]["n"][qi])
        for h in HOLDS:
            t = tabs[h]
            row += " %6s %6s %6s %6s %6s %6s |" % (
                fmt(t["excess_win_rate"][qi]), fmt(t["excess_return"][qi]),
                fmt(t["avg_return"][qi]), fmt(t["base_avg_return"][qi]),
                fmt(t["mae"][qi]), fmt(t["mfe"][qi]))
        flag = ""
        if tabs[HOLDS[0]]["n"][qi] < MIN_N_QUARTER:
            flag = "  *样本不足"
        elif any(tabs[h]["n"][qi] < MIN_N_QUARTER for h in HOLDS):
            flag = "  *长持有期样本不足"
        print(row + flag)
    return tabs


def print_sign_tests(state: dict, title: str) -> dict:
    print("\n" + "=" * 132)
    print("【%s】符号检验：27 个季度里超额为正的个数（H0: 规则无效 → 正负各半）" % title)
    print("=" * 132)
    print("%-22s %-6s %-10s %8s %8s %9s %9s %9s %9s %9s %9s" % (
        "规则", "持有", "口径", "季度数", "正季度", "占比", "二项p", "均值", "中位数", "标准差", "最差/最好"))
    res: dict = {}
    for rule in RULES:
        for h in HOLDS:
            t = quarter_table(state, rule, h)
            for metric in ("excess_return", "excess_win_rate"):
                blk = sign_test_block(t[metric], t["n"], MIN_N_QUARTER)
                res["%s|%d|%s" % (rule, h, metric)] = blk
            blk = res["%s|%d|excess_return" % (rule, h)]
            for tag in ("all", "suff"):
                b = blk[tag]
                if b is None:
                    continue
                print("%-22s %-6d %-10s %8d %8d %8.0f%% %9.4f %8s %8s %8s  %s/%s" % (
                    RULE_NAMES[rule] if tag == "all" else "", h,
                    "全部季度" if tag == "all" else "n>=100",
                    b["n_quarters"], b["n_positive"], b["share_positive"] * 100,
                    b["p_binom_two_sided"], fmt(b["mean"]), fmt(b["median"]),
                    fmt(b["std"], sign=False), fmt(b["min"]), fmt(b["max"])))
    return res


def print_env(state: dict, env: dict, title: str) -> dict:
    print("\n" + "=" * 132)
    print("【%s】超额 vs 市场环境（沪深300 季度涨跌幅 / 振幅 / 季内最大回撤）" % title)
    print("=" * 132)
    out: dict = {}
    for h in HOLDS:
        t = quarter_table(state, "deep30", h)
        ex = t["excess_return"]
        keep = np.isfinite(ex) & (t["n"] >= MIN_N_QUARTER)
        for name, arr in (("涨跌幅", env["ret"]), ("振幅", env["amp"]), ("最大回撤", env["mdd"])):
            k = keep & np.isfinite(arr)
            pr = pearson(arr[k], ex[k])
            sp = spearman(arr[k], ex[k])
            out["%d|%s" % (h, name)] = {"pearson": round(pr, 4), "spearman": round(sp, 4),
                                        "n": int(k.sum())}
            print("  %2d日超额 vs %-8s  Pearson %+.3f  Spearman %+.3f  (n=%d)" % (
                h, name, pr, sp, int(k.sum())))
        # 按指数涨跌幅三分档
        k = keep & np.isfinite(env["ret"])
        r = env["ret"][k]
        e = ex[k]
        labs = np.array(Q_LABELS)[k]
        order = np.argsort(r)
        thirds = np.array_split(order, 3)
        names = ["跌得最多的1/3", "中间1/3", "涨得最多的1/3"]
        for nm, sel in zip(names, thirds):
            out["%d|档|%s" % (h, nm)] = {
                "mean_excess": round(float(e[sel].mean()), 6),
                "n_positive": int((e[sel] > 0).sum()), "n": int(len(sel)),
                "quarters": list(labs[sel]),
            }
            print("      %-14s 平均超额 %s  正/总 %d/%d  季度: %s" % (
                nm, fmt(float(e[sel].mean())), int((e[sel] > 0).sum()), len(sel),
                ",".join(labs[sel])))
    print("\n  每季度环境标签（沪深300）：")
    for qi, lab in enumerate(Q_LABELS):
        t25 = quarter_table(state, "deep30", 25)
        print("    %-8s 涨跌 %7s%%  振幅 %6s%%  最大回撤 %7s%%   25日超额 %6s%%  (n=%d)" % (
            lab, fmt(env["ret"][qi], sign=True), fmt(env["amp"][qi], sign=False),
            fmt(env["mdd"][qi]), fmt(t25["excess_return"][qi]), t25["n"][qi]))
    return out


def print_earnings(state: dict, title: str, span_key: str = "") -> dict:
    """季报窗口效应：每组减**同季度同组**基线后的超额（按季度加权平均 + 符号检验）。"""
    rk = "rule10" if span_key == "10" else "rule"
    bk = "base10" if span_key == "10" else "base"
    print("\n" + "=" * 132)
    print("【%s】季报披露窗口效应（span=%s 交易日）—— 深水单针 短<=30，减同季度同组基线" % (
        title, span_key or "20"))
    print("=" * 132)
    print("%-6s %-8s %10s %10s %10s %10s %10s %10s" % (
        "持有", "分组", "信号n", "绝对收益%", "同组基线%", "超额%", "超额胜率pp", "正季度/可用"))
    out: dict = {}
    for h in HOLDS:
        r = cell_to_qe(state[rk]["deep30"][str(h)]["n"])
        rw = cell_to_qe(state[rk]["deep30"][str(h)]["win"])
        rs = cell_to_qe(state[rk]["deep30"][str(h)]["sum_ret"])
        bn = cell_to_qe(state[bk][str(h)]["n"])
        bw = cell_to_qe(state[bk][str(h)]["win"])
        bs = cell_to_qe(state[bk][str(h)]["sum_ret"])
        for gi, g in enumerate(EARN_GROUPS):
            n_tot = float(r[:, gi].sum())
            if n_tot <= 0:
                continue
            ar = float(rs[:, gi].sum()) / n_tot
            wr = float(rw[:, gi].sum()) / n_tot
            # 同季度同组基线，按该组信号数加权（避免用不同季度权重比较）
            qn = r[:, gi]
            qbn = bn[:, gi]
            m = (qn > 0) & (qbn > 0)
            bar_w = float((qn[m] * (bs[:, gi][m] / qbn[m])).sum() / qn[m].sum())
            bwr_w = float((qn[m] * (bw[:, gi][m] / qbn[m])).sum() / qn[m].sum())
            # 逐季度超额，做符号统计
            qex = np.full(N_Q, np.nan)
            qex[m] = rs[:, gi][m] / qn[m] - bs[:, gi][m] / qbn[m]
            usable = m & (qn >= MIN_N_QUARTER)
            npos = int((qex[usable] > 0).sum())
            out["%d|%s" % (h, g)] = {
                "n": int(n_tot), "avg_return": round(ar, 6),
                "base_avg_return": round(bar_w, 6), "excess_return": round(ar - bar_w, 6),
                "excess_win_rate": round(wr - bwr_w, 6),
                "n_pos_quarters": npos, "n_usable_quarters": int(usable.sum()),
                "p_binom": round(binom_test_two_sided(npos, int(usable.sum())), 6)
                if usable.sum() else None,
            }
            print("%-6d %-8s %10d %10s %10s %10s %10s %8d/%d" % (
                h, EARN_NAMES[g], int(n_tot), fmt(ar), fmt(bar_w), fmt(ar - bar_w),
                fmt(wr - bwr_w), npos, int(usable.sum())))
    return out


def quarter_table_nl(state: dict, rule: str, hold: int) -> dict:
    """严格不重叠口径的季度表（信号日 + 持有期的卖出日都在同一季度内）。"""
    r = state["rule_nl"][rule][str(hold)]
    b = state["base_nl"][str(hold)]
    n = cell_to_q(r["n"])
    win = cell_to_q(r["win"])
    sret = cell_to_q(r["sum_ret"])
    bn = cell_to_q(b["n"])
    bwin = cell_to_q(b["win"])
    bsret = cell_to_q(b["sum_ret"])
    wr = safe_div(win, n)
    ar = safe_div(sret, n)
    return {
        "n": n, "win_rate": wr, "avg_return": ar,
        "excess_win_rate": wr - safe_div(bwin, bn),
        "excess_return": ar - safe_div(bsret, bn),
    }


def print_nonoverlap(state: dict, title: str) -> dict:
    """符号检验的独立性加固：只用「收益窗口完全落在同一季度内」的信号。

    动机：25/60 日持有会让季度末的信号把收益窗口伸进下一季度，相邻季度的超额因此
    存在序列相关，符号检验的「27 个独立样本」会被高估。这里把窗口跨季的信号全部剔掉，
    27 个季度的收益窗口互不重叠，代价是季度末样本变少（60 日尤其明显）。
    """
    print("\n" + "=" * 132)
    print("【%s】独立性加固：严格不重叠口径（收益窗口不跨季）的符号检验" % title)
    print("=" * 132)
    print("%-22s %-6s %10s %10s %10s %12s %12s %10s" % (
        "规则", "持有", "信号n(合计)", "季度数", "正季度", "均值超额%", "中位超额%", "二项p"))
    out: dict = {}
    for rule in RULES:
        for h in HOLDS:
            t = quarter_table_nl(state, rule, h)
            for metric in ("excess_return", "excess_win_rate"):
                blk = sign_test_block(t[metric], t["n"], MIN_N_QUARTER)["suff"]
                out["%s|%d|%s" % (rule, h, metric)] = blk
            b = out["%s|%d|excess_return" % (rule, h)]
            if b is None:
                continue
            print("%-22s %-6d %10d %10d %10d %12s %12s %10.4f" % (
                RULE_NAMES[rule], h, int(np.nansum(t["n"])), b["n_quarters"], b["n_positive"],
                fmt(b["mean"]), fmt(b["median"]), b["p_binom_two_sided"]))
    print("\n  深水单针 短<=30 的逐季度不重叠超额（25 日）：")
    t = quarter_table_nl(state, "deep30", 25)
    row = ""
    for qi, lab in enumerate(Q_LABELS):
        row += "%s %s(n=%d)  " % (lab, fmt(t["excess_return"][qi]), t["n"][qi])
        if (qi + 1) % 3 == 0:
            print("    " + row)
            row = ""
    if row:
        print("    " + row)
    return out


def print_survivorship(fwd: dict) -> dict:
    print("\n" + "=" * 132)
    print("幸存者偏差量化：每季度「本地有数据且满足 >=120 根前置 K 线」的沪深个股数 vs 公开上市家数")
    print("=" * 132)
    st = fwd["state"]
    sym = np.asarray(st["sym_per_q"], dtype=np.int64)
    fm = fwd["file_meta"]
    firsts = np.array([v["first"] for v in fm.values()], dtype=np.int64)
    lasts = np.array([v["last"] for v in fm.values()], dtype=np.int64)
    out = {"per_quarter": {}, "note": LISTED_REF_NOTE}
    print("%-8s %10s %12s %10s" % ("季度", "本地股票数", "公开近似值", "缺口%"))
    for qi, lab in enumerate(Q_LABELS):
        ref = LISTED_REF_HS.get(lab)
        gap = "  n/a"
        if ref:
            gap = "%+.1f%%" % (100.0 * (sym[qi] - ref) / ref)
        print("%-8s %10d %12s %10s" % (lab, sym[qi], ref if ref else "-", gap))
        out["per_quarter"][lab] = {"local": int(sym[qi]), "ref": ref}
    n_mid = int(((lasts >= 20200101) & (lasts <= 20260801)).sum())
    n_pre = int((lasts < 20200101).sum())
    n_cur = int((lasts == 20260828).sum())
    print("\n  本地文件末日分布：仍在交易(=2026-08-28) %d 只；期间内停更(2020-01~2026-08) %d 只；"
          "2020 前就停更 %d 只" % (n_cur, n_mid, n_pre))
    print("  → 本地 hsjday **保留了 %d 只期间内退市/长期停牌的个股**，不是纯「当前成分」快照。" % n_mid)
    print("  首个交易日 < 2020-01-01 的股票：%d / %d（%.1f%%）" % (
        int((firsts < 20200101).sum()), len(firsts), 100.0 * (firsts < 20200101).mean()))
    out.update({"n_current": n_cur, "n_stopped_in_period": n_mid, "n_stopped_before": n_pre,
                "n_first_before_2020": int((firsts < 20200101).sum()),
                "n_files": len(firsts)})
    return out


def print_adjust_compare(fwd: dict, non: dict) -> dict:
    print("\n" + "=" * 132)
    print("复权对照：前复权（主口径）vs 未复权（阶段 12/13/14 口径）——结论方向是否一致")
    print("=" * 132)
    out: dict = {}
    print("%-6s %-10s %10s %10s %12s %12s %10s" % (
        "持有", "口径", "季度数", "正季度", "均值超额%", "中位数超额%", "二项p"))
    for h in HOLDS:
        for tag, st in (("前复权", fwd["state"]), ("未复权", non["state"])):
            t = quarter_table(st, "deep30", h)
            b = sign_test_block(t["excess_return"], t["n"], MIN_N_QUARTER)["suff"]
            out["%d|%s" % (h, tag)] = b
            print("%-6d %-10s %10d %10d %12s %12s %10.4f" % (
                h, tag, b["n_quarters"], b["n_positive"], fmt(b["mean"]),
                fmt(b["median"]), b["p_binom_two_sided"]))
    # 逐季度符号一致性
    for h in HOLDS:
        tf = quarter_table(fwd["state"], "deep30", h)
        tn = quarter_table(non["state"], "deep30", h)
        k = np.isfinite(tf["excess_return"]) & np.isfinite(tn["excess_return"]) & (tf["n"] >= MIN_N_QUARTER)
        same = int((np.sign(tf["excess_return"][k]) == np.sign(tn["excess_return"][k])).sum())
        mad = float(np.abs(tf["excess_return"][k] - tn["excess_return"][k]).mean())
        out["sign_agree|%d" % h] = {"same": same, "n": int(k.sum()), "mean_abs_diff": round(mad, 6)}
        print("  %2d日：逐季度超额符号一致 %d/%d，平均绝对差 %.3fpp" % (h, same, int(k.sum()), mad * 100))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--forward", default="data/stage15_forward_hs.json")
    ap.add_argument("--none", dest="none_path", default="data/stage15_none_hs.json")
    ap.add_argument("--forward-all", default="data/stage15_forward_all.json")
    ap.add_argument("--out", default="data/stage15_analysis.json")
    args = ap.parse_args()

    fwd = json.loads(Path(args.forward).read_text(encoding="utf-8"))
    non = json.loads(Path(args.none_path).read_text(encoding="utf-8"))
    print("主口径 meta：%s" % fwd["meta"])
    print("对照 meta：%s" % non["meta"])

    analysis: dict = {"meta": {"forward": fwd["meta"], "none": non["meta"]}}
    tabs = print_quarter_tables(fwd["state"], "前复权 / 沪深")
    analysis["quarter_table_deep30"] = {
        str(h): {k: (v.tolist() if isinstance(v, np.ndarray) else v)
                 for k, v in quarter_table(fwd["state"], "deep30", h).items()}
        for h in HOLDS
    }
    analysis["quarter_table_orig"] = {
        str(h): {k: (v.tolist() if isinstance(v, np.ndarray) else v)
                 for k, v in quarter_table(fwd["state"], "orig", h).items()}
        for h in HOLDS
    }
    analysis["sign_tests"] = print_sign_tests(fwd["state"], "前复权 / 沪深")

    # 对照组：原始单针的逐季度表（只打 25 日，节省篇幅）
    print("\n" + "=" * 132)
    print("对照组：原始单针（趋势多头 + 长期>=80 + 短期<=30）逐季度 25 日超额")
    print("=" * 132)
    t = quarter_table(fwd["state"], "orig", 25)
    t20 = quarter_table(fwd["state"], "deep30", 25)
    row = ""
    for qi, lab in enumerate(Q_LABELS):
        row += "%s %s%s(n=%d)  " % (lab, fmt(t["excess_return"][qi]),
                                    "*" if t["n"][qi] < MIN_N_QUARTER else "", t["n"][qi])
        if (qi + 1) % 3 == 0:
            print("  " + row)
            row = ""
    if row:
        print("  " + row)

    env300 = index_quarter_env(INDEX_HS300)
    envsse = index_quarter_env(INDEX_SSE)
    analysis["env_hs300"] = {k: v.tolist() for k, v in env300.items()}
    analysis["env_sse"] = {k: v.tolist() for k, v in envsse.items()}
    analysis["env_corr_hs300"] = print_env(fwd["state"], env300, "前复权 / 沪深")
    print("\n  （上证指数口径的相关系数）")
    analysis["env_corr_sse"] = {}
    for h in HOLDS:
        tt = quarter_table(fwd["state"], "deep30", h)
        ex = tt["excess_return"]
        keep = np.isfinite(ex) & (tt["n"] >= MIN_N_QUARTER)
        for name, arr in (("涨跌幅", envsse["ret"]), ("振幅", envsse["amp"]), ("最大回撤", envsse["mdd"])):
            k = keep & np.isfinite(arr)
            analysis["env_corr_sse"]["%d|%s" % (h, name)] = {
                "pearson": round(pearson(arr[k], ex[k]), 4),
                "spearman": round(spearman(arr[k], ex[k]), 4), "n": int(k.sum())}
            print("    %2d日超额 vs %-8s Pearson %+.3f Spearman %+.3f (n=%d)" % (
                h, name, pearson(arr[k], ex[k]), spearman(arr[k], ex[k]), int(k.sum())))

    analysis["earnings_span20"] = print_earnings(fwd["state"], "前复权 / 沪深", "")
    analysis["earnings_span10"] = print_earnings(fwd["state"], "前复权 / 沪深", "10")
    if "rule_nl" in fwd["state"]:
        analysis["nonoverlap"] = print_nonoverlap(fwd["state"], "前复权 / 沪深")
    analysis["survivorship"] = print_survivorship(fwd)
    analysis["adjust_compare"] = print_adjust_compare(fwd, non)

    fa_path = Path(args.forward_all)
    if fa_path.exists():
        fa = json.loads(fa_path.read_text(encoding="utf-8"))
        print("\n" + "=" * 132)
        print("稳健性对照：含北交所（%d 只）vs 只沪深（%d 只）" % (
            fa["meta"]["n_symbols_processed"], fwd["meta"]["n_symbols_processed"]))
        print("=" * 132)
        analysis["universe_compare"] = {}
        for h in HOLDS:
            ta = quarter_table(fa["state"], "deep30", h)
            th = quarter_table(fwd["state"], "deep30", h)
            ba = sign_test_block(ta["excess_return"], ta["n"], MIN_N_QUARTER)["suff"]
            bh = sign_test_block(th["excess_return"], th["n"], MIN_N_QUARTER)["suff"]
            analysis["universe_compare"]["%d" % h] = {"all": ba, "hs": bh}
            print("  %2d日：含北交所 正%d/%d 均值%s 中位%s p=%.4f | 只沪深 正%d/%d 均值%s 中位%s p=%.4f" % (
                h, ba["n_positive"], ba["n_quarters"], fmt(ba["mean"]), fmt(ba["median"]),
                ba["p_binom_two_sided"], bh["n_positive"], bh["n_quarters"], fmt(bh["mean"]),
                fmt(bh["median"]), bh["p_binom_two_sided"]))

    Path(args.out).write_text(json.dumps(analysis, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n分析快照已写入 %s" % args.out)


if __name__ == "__main__":
    main()
