#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 docs/阶段15-报告.md 里的全部数据表（Markdown），避免手抄数字出错。

只读现有 JSON：stage15_analysis.json / stage15_bias_check.json /
stage15_orig_regime.json / stage15_regime_switch.json / stage15_forward_hs.json（补 deep20 逐季度）。
输出到 stdout。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.analyze_stage15 import quarter_table  # noqa: E402

D = json.loads((ROOT / "data" / "stage15_analysis.json").read_text())
BC = json.loads((ROOT / "data" / "stage15_bias_check.json").read_text())
OR = json.loads((ROOT / "data" / "stage15_orig_regime.json").read_text())
SW = json.loads((ROOT / "data" / "stage15_regime_switch.json").read_text())
L = D["meta"]["forward"]["quarters"]
RN = {"deep30": "deep30 = 深水单针（短≤30 / 长≤55，非趋势多头）",
      "deep20": "deep20 = 深水单针加严版（短≤20 / 长≤55）",
      "orig": "orig = 原始单针（趋势多头 + 长期随机≥80 + 短≤30）"}


def p(x, dec=2):
    return "n/a" if x is None or (isinstance(x, float) and not np.isfinite(x)) else ("%+.*f%%" % (dec, x * 100))


def pu(x, dec=2):
    return "n/a" if x is None or (isinstance(x, float) and not np.isfinite(x)) else ("%.*f%%" % (dec, x * 100))


def n_fmt(x):
    return "0" if x in (None, 0) or not np.isfinite(x) else "{:,}".format(int(x))


def deep20_table():
    st = json.loads((ROOT / "data" / "stage15_forward_hs.json").read_text())["state"]
    return {str(h): quarter_table(st, "deep20", h) for h in (20, 25, 60)}


def sec1():
    print("<!-- BEGIN AUTO: sign_summary -->")
    print("| 规则 | 持有 | 指标 | 正/总 | 占比 | p(二项双侧) | 均值 | 中位数 | 标准差 | 最差季 | 最好季 | 27季合计 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in ("deep30", "deep20", "orig"):
        for h in ("20", "25", "60"):
            for m, mn in (("excess_win_rate", "超额胜率"), ("excess_return", "超额收益")):
                b = D["sign_tests"]["%s|%s|%s" % (r, h, m)]["all"]
                star = " ✅" if b["p_binom_two_sided"] < 0.05 and b["mean"] > 0 else (
                    " ❌" if b["p_binom_two_sided"] < 0.05 and b["mean"] < 0 else "")
                print("| %s | %s日 | %s | **%d/%d**%s | %.1f%% | **%.4f** | %s | %s | %s | %s | %s | %s |" % (
                    r, h, mn, b["n_positive"], b["n_quarters"], star, b["share_positive"] * 100,
                    b["p_binom_two_sided"], p(b["mean"]), p(b["median"]), pu(b["std"]),
                    p(b["min"]), p(b["max"]), p(b["sum"], 1)))
    print("<!-- END AUTO -->\n")

    print("<!-- BEGIN AUTO: concentration -->")
    print("| 规则 | 持有 | 指标 | 前3季占正超额之和 | 前3季占27季总和 |")
    print("|---|---|---|---|---|")
    for r in ("deep30", "deep20", "orig"):
        for h in ("20", "25", "60"):
            for m, mn in (("excess_return", "超额收益"), ("excess_win_rate", "超额胜率")):
                b = D["sign_tests"]["%s|%s|%s" % (r, h, m)]["all"]
                print("| %s | %s日 | %s | %s | %s |" % (
                    r, h, mn, pu(b["top3_share_of_positive_sum"], 1), pu(b["top3_share_of_total_sum"], 1)))
    print("<!-- END AUTO -->\n")

    d20 = deep20_table()
    for r in ("deep30", "deep20", "orig"):
        t = d20 if r == "deep20" else {h: D["quarter_table_%s" % r][h] for h in ("20", "25", "60")}
        print("<!-- BEGIN AUTO: perquarter_%s -->" % r)
        print("**%s**\n" % RN[r])
        print("| 季度 | 信号数(20日) | 20日超额收益 | 20日超额胜率 | 25日超额收益 | 25日超额胜率 | 60日超额收益 | 60日超额胜率 |")
        print("|---|---|---|---|---|---|---|---|")
        for i, q in enumerate(L):
            n = t["20"]["n"][i]
            n = None if n is None else float(n)
            flag = " ⚠小样本" if (n is None or n < 1000) else ""
            cells = []
            for h in ("20", "25", "60"):
                cells += [p(t[h]["excess_return"][i]), p(t[h]["excess_win_rate"][i])]
            print("| %s%s | %s | %s |" % (q, flag, n_fmt(n), " | ".join(cells)))
        tot = {h: int(np.nansum(np.array(t[h]["n"], dtype=float))) for h in ("20", "25", "60")}
        mn = {h: int(np.nanmin(np.array(t[h]["n"], dtype=float))) for h in ("20", "25", "60")}
        print("\n信号总数：20日 %s / 25日 %s / 60日 %s；最小季度信号数：20日 %s / 25日 %s / 60日 %s\n" % (
            "{:,}".format(tot["20"]), "{:,}".format(tot["25"]), "{:,}".format(tot["60"]),
            "{:,}".format(mn["20"]), "{:,}".format(mn["25"]), "{:,}".format(mn["60"])))
        print("<!-- END AUTO -->\n")


def sec2():
    print("<!-- BEGIN AUTO: env_corr -->")
    print("| 持有 | 环境变量 | Pearson | Spearman | n |")
    print("|---|---|---|---|---|")
    for h in ("20", "25", "60"):
        for nm in ("涨跌幅", "振幅", "最大回撤"):
            v = D["env_corr_hs300"]["%s|%s" % (h, nm)]
            print("| %s日 | 沪深300 %s | **%+.3f** | **%+.3f** | %d |" % (h, nm, v["pearson"], v["spearman"], v["n"]))
    for h in ("20", "25", "60"):
        v = D["env_corr_sse"]["%s|涨跌幅" % h]
        print("| %s日 | 上证 涨跌幅 | %+.3f | %+.3f | %d |" % (h, v["pearson"], v["spearman"], v["n"]))
    print("<!-- END AUTO -->\n")

    print("<!-- BEGIN AUTO: env_tercile -->")
    print("| 持有 | 档位 | 平均超额收益 | 正/总 | 季度名单 |")
    print("|---|---|---|---|---|")
    for h in ("20", "25", "60"):
        for nm in ("跌得最多的1/3", "中间1/3", "涨得最多的1/3"):
            v = D["env_corr_hs300"]["%s|档|%s" % (h, nm)]
            print("| %s日 | %s | **%s** | %d/%d | %s |" % (
                h, nm, p(v["mean_excess"]), v["n_positive"], v["n"], "、".join(v["quarters"])))
    print("<!-- END AUTO -->\n")

    print("<!-- BEGIN AUTO: env_timeline -->")
    print("| 季度 | 沪深300涨跌 | 沪深300振幅 | 沪深300季内最大回撤 | 上证涨跌 | deep30 20日超额 | deep30 25日超额 | 环境档位(20日) |")
    print("|---|---|---|---|---|---|---|---|")
    band = {}
    for nm in ("跌得最多的1/3", "中间1/3", "涨得最多的1/3"):
        for q in D["env_corr_hs300"]["20|档|%s" % nm]["quarters"]:
            band[q] = nm
    t20, t25 = D["quarter_table_deep30"]["20"], D["quarter_table_deep30"]["25"]
    e, s = D["env_hs300"], D["env_sse"]
    for i, q in enumerate(L):
        print("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            q, p(e["ret"][i]), pu(e["amp"][i]), p(e["mdd"][i]), p(s["ret"][i]),
            p(t20["excess_return"][i]), p(t25["excess_return"][i]), band.get(q, "-")))
    print("<!-- END AUTO -->\n")


def sec3():
    print("<!-- BEGIN AUTO: earnings -->")
    print("| span | 持有 | 分组 | 信号数 | 绝对收益 | 同组基线 | 超额收益 | 超额胜率 | 正季度/可用季度 | p(二项) |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    names = {"pre": "披露前", "in": "披露窗口内", "post": "披露后", "other": "其他时段"}
    for span, key in (("20日", "earnings_span20"), ("10日", "earnings_span10")):
        for h in ("20", "25", "60"):
            for g in ("pre", "in", "post", "other"):
                v = D[key]["%s|%s" % (h, g)]
                print("| %s | %s日 | %s | %s | %s | %s | **%s** | %s | %d/%d | %.4f |" % (
                    span, h, names[g], "{:,}".format(v["n"]), p(v["avg_return"]),
                    p(v["base_avg_return"]), p(v["excess_return"]), p(v["excess_win_rate"]),
                    v["n_pos_quarters"], v["n_usable_quarters"], v["p_binom"]))
    print("<!-- END AUTO -->\n")


def sec4():
    sv = D["survivorship"]
    print("<!-- BEGIN AUTO: survivorship -->")
    print("| 季度 | 本地有数据股票数 | 公开上市家数(近似) | 差额 | 缺口比例 |")
    print("|---|---|---|---|---|")
    for q in L:
        v = sv["per_quarter"][q]
        if v["ref"]:
            print("| %s | %d | %d | %d | %.1f%% |" % (q, v["local"], v["ref"],
                                                      v["ref"] - v["local"], (v["ref"] - v["local"]) / v["ref"] * 100))
        else:
            print("| %s | %d | — | — | — |" % (q, v["local"]))
    print("<!-- END AUTO -->\n")

    print("<!-- BEGIN AUTO: bias_counts -->")
    c = BC["counts"]
    for k, lab in (("signals_total", "信号总数（25日口径）"), ("kept", "保留"),
                   ("dropped_A_stopped", "A 类丢弃：持有期内股票数据终止（退市/停牌）"),
                   ("dropped_B_dataend", "B 类丢弃：持有期越过数据末日 2026-08-28"),
                   ("signals_from_stopped_symbols", "来自 225 只期间内终止股票的信号数"),
                   ("n_stopped_symbols_with_signals", "其中出过信号的股票数")):
        print("- %s：**%s**" % (lab, "{:,}".format(c[k])))
    print("<!-- END AUTO -->\n")

    print("<!-- BEGIN AUTO: bias_sens -->")
    print("| 情景 | 正/总 | p | 均值超额 | 中位数超额 |")
    print("|---|---|---|---|---|")
    for k, v in BC["sign_test_summary"].items():
        print("| %s | **%d/%d** | %.4f | %s | %s |" % (k, v["n_positive"], v["n_quarters"], v["p"],
                                                       p(v["mean"]), p(v["median"])))
    print("<!-- END AUTO -->\n")

    print("<!-- BEGIN AUTO: bias_perquarter -->")
    print("| 季度 | 信号数 | A类补回条数 | 原口径超额 | 补回(不冲击) | 补回(-50%) | 补回(-80%) |")
    print("|---|---|---|---|---|---|---|")
    for q in L:
        v = BC["per_quarter"][q]
        print("| %s | %s | %d | %s | %s | %s | %s |" % (
            q, "{:,}".format(v["n"]), v["dropA_n"], p(v["excess"]), p(v["raw"]),
            p(v["shock50"]), p(v["shock80"])))
    print("<!-- END AUTO -->\n")


def sec5():
    print("<!-- BEGIN AUTO: adjust -->")
    print("| 持有 | 口径 | 正/总 | p | 均值 | 中位数 | 最差 | 最好 | 逐季度同号数 | 平均绝对差 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for h in ("20", "25", "60"):
        ag = D["adjust_compare"]["sign_agree|%s" % h]
        for k in ("前复权", "未复权"):
            b = D["adjust_compare"]["%s|%s" % (h, k)]
            print("| %s日 | %s | **%d/%d** | %.4f | %s | %s | %s | %s | %d/%d | %s |" % (
                h, k, b["n_positive"], b["n_quarters"], b["p_binom_two_sided"], p(b["mean"]),
                p(b["median"]), p(b["min"]), p(b["max"]), ag["same"], ag["n"], p(ag["mean_abs_diff"], 3)))
    print("<!-- END AUTO -->\n")

    print("<!-- BEGIN AUTO: universe -->")
    print("| 持有 | 宇宙 | 正/总 | p | 均值 | 中位数 |")
    print("|---|---|---|---|---|---|")
    for h in ("20", "25", "60"):
        for k, lab in (("hs", "沪深（主口径）"), ("all", "沪深+北交所")):
            b = D["universe_compare"][h][k]
            print("| %s日 | %s | **%d/%d** | %.4f | %s | %s |" % (
                h, lab, b["n_positive"], b["n_quarters"], b["p_binom_two_sided"], p(b["mean"]), p(b["median"])))
    print("<!-- END AUTO -->\n")


def sec6():
    print("<!-- BEGIN AUTO: nonoverlap -->")
    print("| 规则 | 持有 | 指标 | 原口径 正/总 (p) | 严格不重叠 正/总 (p) | 不重叠可用季度 | 不重叠均值 |")
    print("|---|---|---|---|---|---|---|")
    for r in ("deep30", "deep20", "orig"):
        for h in ("20", "25", "60"):
            for m, mn in (("excess_win_rate", "超额胜率"), ("excess_return", "超额收益")):
                k = "%s|%s|%s" % (r, h, m)
                a = D["sign_tests"][k]["all"]
                b = D["nonoverlap"][k]
                print("| %s | %s日 | %s | %d/%d (%.4f) | **%d/%d** (%.4f) | %d | %s |" % (
                    r, h, mn, a["n_positive"], a["n_quarters"], a["p_binom_two_sided"],
                    b["n_positive"], b["n_quarters"], b["p_binom_two_sided"], b["n_quarters"], p(b["mean"])))
    print("<!-- END AUTO -->\n")


def sec7():
    print("<!-- BEGIN AUTO: orig_regime -->")
    print("| 持有 | 档位 | 季度数 | deep30 平均超额 | orig 平均超额 | orig 超额胜率 | orig 正/总 |")
    print("|---|---|---|---|---|---|---|")
    for h in ("20", "25", "60"):
        for nm in ("跌得最多的1/3", "中间1/3", "涨得最多的1/3"):
            v = OR["%s|档|%s" % (h, nm)]
            bo, bw = v["orig_excess_return"], v["orig_excess_win_rate"]
            print("| %s日 | %s | %d | **%s** | **%s** | %s | %d/%d |" % (
                h, nm, v["deep30_excess_return"]["n_quarters"], p(v["deep30_excess_return"]["mean"]),
                p(bo["mean"]) if bo else "n/a", p(bw["mean"]) if bw else "n/a",
                bo["n_positive"] if bo else 0, bo["n_quarters"] if bo else 0))
    print("<!-- END AUTO -->\n")

    print("<!-- BEGIN AUTO: orig_up9 -->")
    v = OR["20|档|涨得最多的1/3"]["orig_per_quarter"]
    print("| 季度 | 沪深300涨跌 | orig 信号数 | orig 20日超额收益 | orig 20日超额胜率 |")
    print("|---|---|---|---|---|")
    for q in OR["20|档|涨得最多的1/3"]["quarters"]:
        r = v[q]
        print("| %s | %s | %s | **%s** | %s |" % (q, p(r["hs300_ret"]), n_fmt(r["n"]),
                                                  p(r["excess_return"]), p(r["excess_win_rate"])))
    print("<!-- END AUTO -->\n")

    print("<!-- BEGIN AUTO: orig_corr -->")
    print("| 持有 | orig 超额收益 vs 沪深300涨跌 | orig 超额胜率 vs 沪深300涨跌 | deep30 超额收益 vs 沪深300涨跌 | corr(deep30超额, orig超额) |")
    print("|---|---|---|---|---|")
    for h in ("20", "25", "60"):
        c = OR["%s|corr" % h]
        dc = D["env_corr_hs300"]["%s|涨跌幅" % h]
        sc = SW[h]["corr_deep30_vs_orig"]
        print("| %s日 | Pearson %+.3f / Spearman %+.3f | Pearson %+.3f / Spearman %+.3f | Pearson %+.3f / Spearman %+.3f | Pearson %+.3f / Spearman %+.3f |" % (
            h, c["excess_return"]["pearson"], c["excess_return"]["spearman"],
            c["excess_win_rate"]["pearson"], c["excess_win_rate"]["spearman"],
            dc["pearson"], dc["spearman"], sc["pearson"], sc["spearman"]))
    print("<!-- END AUTO -->\n")

    print("<!-- BEGIN AUTO: switch -->")
    print("| 持有 | 方案 | 正/总 | p | 平均季度超额 | 中位数 | 27季合计 |")
    print("|---|---|---|---|---|---|---|")
    labs = {"always_deep30": "始终深水单针", "always_orig": "始终原始单针",
            "switch_lookahead_tercile": "切换：同期分档上1/3用orig（⚠含前视）",
            "switch_lookahead_sign": "切换：同期指数收涨就用orig（⚠含前视）",
            "switch_lagged_prev_quarter": "切换：上一季涨>3%用orig（可执行）"}
    for h in ("20", "25", "60"):
        for k in ("always_deep30", "always_orig", "switch_lookahead_tercile",
                  "switch_lookahead_sign", "switch_lagged_prev_quarter"):
            b = SW[h][k]
            print("| %s日 | %s | **%d/%d** | %.6f | %s | %s | %s |" % (
                h, labs[k], b["n_positive"], b["n_quarters"], b["p_binom_two_sided"],
                p(b["mean"]), p(b["median"]), p(b["sum"], 1)))
    print("<!-- END AUTO -->\n")

    print("<!-- BEGIN AUTO: bysign -->")
    print("| 持有 | 规则 | 指数收涨季度 | 指数收跌季度 |")
    print("|---|---|---|---|")
    for h in ("20", "25", "60"):
        s = SW[h]["by_index_sign"]
        for r, ku, kd in (("deep30", "deep30_up", "deep30_down"), ("orig", "orig_up", "orig_down")):
            print("| %s日 | %s | %s（%d/%d 正） | %s（%d/%d 正） |" % (
                h, r, p(s[ku]["mean"]), s[ku]["n_positive"], s[ku]["n_quarters"],
                p(s[kd]["mean"]), s[kd]["n_positive"], s[kd]["n_quarters"]))
    print("<!-- END AUTO -->\n")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    fns = {"1": sec1, "2": sec2, "3": sec3, "4": sec4, "5": sec5, "6": sec6, "7": sec7}
    for k in (fns if which == "all" else [which]):
        print("\n@@@@@ SECTION %s @@@@@\n" % k)
        fns[k]()
