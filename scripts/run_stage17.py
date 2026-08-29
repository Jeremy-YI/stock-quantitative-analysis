#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 17 任务 3/4：ETF 宇宙上的「深水单针（deep30）+ 阶段16 弱势过滤器」核心重测 + 个股对照。

口径（见 docs/阶段17-进度.md）：
- 宇宙：标准场内 ETF，流动性过滤（滚动60日均成交额）+ 相关性去重（60日日收益 Pearson 聚簇，每簇留成交额最大一只），
  每月首个交易日重平衡（point-in-time）。
- 信号：deep30 = 非趋势多头 + 短期随机(3日)≤30 + 长期随机(20日)≤55；deep20 = ≤20 加严版。
  信号日收盘买，持有 20/25/60 日。指标复用 pin30_common.pin30_series（前复权）。
- 基线 = 同期同组 ETF 等权基线（dedup 后的代表 ETF，按分组分别算）。
  超额 = 信号收益 − 同季度同持有期同组基线。
- 阶段16 过滤器：只在「沪深300 滚动60日涨跌幅 < 0」时做 deep30。
- MAE/MFE = min(low)/max(high) 口径（阶段12b 逐字一致）。
- 符号检验 = 二项精确双侧（27 季度 2020Q1~2026Q3）。

用法：
    .venv/bin/python scripts/run_stage17.py --out data/stage17_results.json
"""
from __future__ import annotations

import argparse
import json
import math
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
from scripts.pin30_common import pin30_series
from scripts.stage17_classify import GROUP_LABELS, classify_symbol, load_names

PANEL_START = date(2019, 1, 1)
PERIOD_START = date(2020, 1, 1)
PERIOD_END = date(2026, 8, 28)
HOLDS = (20, 25, 60)
SHORT_PIN = 30.0
SHORT_PIN20 = 20.0
LONG_DEEP_MAX = 55.0
MIN_HIST_BARS = 120
INDEX_HS300 = "sh000300"
EQUITY_GROUPS = ("broad", "sector", "commodity", "qdii", "style")  # 剔除 bond

MAIN_COMBO = "liq_50M_rho_0.95"


def binom_two_sided(k: int, n: int, p: float = 0.5) -> float:
    if n <= 0:
        return float("nan")
    pmf = lambda i: math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
    obs = pmf(k)
    return min(1.0, sum(pmf(i) for i in range(n + 1) if pmf(i) <= obs + 1e-15))


def build_quarters() -> list[dict]:
    out = []
    for year in range(PERIOD_START.year, PERIOD_END.year + 1):
        for q, (m0, m1) in enumerate(((1, 3), (4, 6), (7, 9), (10, 12)), start=1):
            qs = date(year, m0, 1)
            qe = date(year, m1, 31) if m1 in (3, 12) else date(year, m1, 30)
            if qe < PERIOD_START or qs > PERIOD_END:
                continue
            out.append({"label": "%dQ%d" % (year, q), "start": max(qs, PERIOD_START),
                        "end": min(qe, PERIOD_END)})
    return out


QUARTERS = build_quarters()
N_Q = len(QUARTERS)
_Q_START_ORD = np.array([q["start"].toordinal() for q in QUARTERS], dtype=np.int64)


def quarter_id(ordinals: np.ndarray) -> np.ndarray:
    return np.searchsorted(_Q_START_ORD, ordinals, side="right") - 1


def master_calendar(root: Path) -> tuple[np.ndarray, np.ndarray]:
    sse = parse_day_file(root / "sh" / "lday" / "sh000001.day")
    ords = np.array([d.toordinal() for d in sse["date"].to_numpy()], dtype=np.int64)
    lo, hi = PANEL_START.toordinal(), PERIOD_END.toordinal()
    m = (ords >= lo) & (ords <= hi)
    return sse["date"].to_numpy()[m], ords[m]


def load_hs300_r60(root: Path, cal_ord: np.ndarray) -> np.ndarray:
    """沪深300 滚动 60 日涨跌幅，对齐到 master calendar（ffill），返回 (n_days,) 数组。"""
    hs = parse_day_file(root / "sh" / "lday" / "sh000300.day")
    hs = hs.set_index("date")["close"].astype(float)
    cal_dates = [date.fromordinal(int(o)) for o in cal_ord]
    close = hs.reindex(cal_dates).ffill().to_numpy(dtype=float)
    n = len(close)
    r60 = np.full(n, np.nan)
    for i in range(60, n):
        r60[i] = close[i] / close[i - 60] - 1.0
    return r60


def sign_block(vals: np.ndarray) -> dict:
    v = vals[np.isfinite(vals)]
    n = len(v)
    k = int((v > 0).sum())
    return {"n_quarters": n, "n_positive": k, "p_binom": round(binom_two_sided(k, n), 6),
            "mean": round(float(v.mean()), 6) if n else None,
            "median": round(float(np.median(v)), 6) if n else None,
            "sum": round(float(v.sum()), 6) if n else None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/stage17_results.json")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    root = resolve_hsjday_root()
    t0 = time.time()

    names = load_names()
    univ_json = json.loads((ROOT / "data" / "stage17_universe.json").read_text(encoding="utf-8"))
    combos = univ_json["combinations"]

    cal_date, cal_ord = master_calendar(root)
    n_days = len(cal_ord)
    print("交易日历 %d 天（2019-01-01 ~ 2026-08-28）" % n_days)
    r60 = load_hs300_r60(root, cal_ord)

    # 所有组合的 ever_in 并集（仅权益类）
    union = set()
    for v in combos.values():
        union |= set(v["ever_in"].keys())
    syms = []
    for sym in sorted(union):
        g, _ = classify_symbol(sym, names)
        if g in EQUITY_GROUPS:
            syms.append(sym)
    if args.limit:
        syms = syms[: args.limit]
    n_etf = len(syms)
    print("权益类 ETF 并集 %d 只" % n_etf)

    # ---- 逐 ETF 解析 + 指标 + 对齐到日历 ----
    cal_close = np.full((n_days, n_etf), np.nan)
    cal_high = np.full((n_days, n_etf), np.nan)
    cal_low = np.full((n_days, n_etf), np.nan)
    cal_amt60 = np.full((n_days, n_etf), np.nan)
    group_id = np.zeros(n_etf, dtype=np.int8)
    group_list = list(EQUITY_GROUPS)
    g2i = {g: i for i, g in enumerate(group_list)}

    # 信号记录：{rule: {field: []}}，逐 ETF append
    sig_fields = ("etf", "date", "qid", "cal_idx")
    signals = {r: {f: [] for f in sig_fields} for r in ("deep30", "deep20")}

    for j, sym in enumerate(syms):
        g, _ = classify_symbol(sym, names)
        group_id[j] = g2i[g]
        m, code = sym[:2], sym[2:]
        try:
            df = parse_day_file(root / m / "lday" / ("%s.day" % sym))
        except FileNotFoundError:
            continue
        if df.empty:
            continue
        df = forward_adjust_frame(df, sym)
        s = pin30_series(df)
        close = s["close"]
        short = s["short"]
        long_ = s["long"]
        trend = s["trend"]
        own_ord = np.array([d.toordinal() for d in df["date"].to_numpy()], dtype=np.int64)
        n = len(df)

        # 对齐到日历（ffill）
        own_dates = df["date"].to_numpy()
        cc = pd.Series(df["close"].astype(float).to_numpy(), index=own_dates)
        ch = pd.Series(df["high"].astype(float).to_numpy(), index=own_dates)
        cl = pd.Series(df["low"].astype(float).to_numpy(), index=own_dates)
        cal_dates = [date.fromordinal(int(o)) for o in cal_ord]
        cal_close[:, j] = cc.reindex(cal_dates).ffill().to_numpy(dtype=float)
        cal_high[:, j] = ch.reindex(cal_dates).ffill().to_numpy(dtype=float)
        cal_low[:, j] = cl.reindex(cal_dates).ffill().to_numpy(dtype=float)
        amt60_own = pd.Series(df["amount"].astype(float).to_numpy()).rolling(60, min_periods=60).mean().to_numpy()
        cal_amt60[:, j] = pd.Series(amt60_own, index=own_dates).reindex(cal_dates).ffill().to_numpy(dtype=float)

        i0 = int(np.searchsorted(own_ord, PERIOD_START.toordinal(), side="left"))
        i1 = int(np.searchsorted(own_ord, PERIOD_END.toordinal(), side="right"))
        i0 = max(i0, MIN_HIST_BARS)
        if i1 - i0 < 1:
            continue

        idx = np.arange(i0, i1, dtype=np.int64)
        not_trend = ~trend[idx]
        m_deep30 = not_trend & (short[idx] <= SHORT_PIN) & (long_[idx] <= LONG_DEEP_MAX)
        m_deep20 = not_trend & (short[idx] <= SHORT_PIN20) & (long_[idx] <= LONG_DEEP_MAX)
        masks = {"deep30": m_deep30, "deep20": m_deep20}

        for rule, mm in masks.items():
            if not mm.any():
                continue
            si = idx[mm]
            sig_dates = own_ord[si]
            cal_idx = np.searchsorted(cal_ord, sig_dates, side="left")
            cal_idx = np.clip(cal_idx, 0, n_days - 1)
            signals[rule]["etf"].append(np.full(si.size, j, dtype=np.int16))
            signals[rule]["date"].append(sig_dates)
            signals[rule]["qid"].append(quarter_id(sig_dates))
            signals[rule]["cal_idx"].append(cal_idx)

    print("解析 + 指标完成 %.1fs" % (time.time() - t0))

    # ---- 前向收益面板（日历口径）----
    cal_fwd = {}
    cal_mfe = {}
    cal_mae = {}
    for h in HOLDS:
        cc = pd.DataFrame(cal_close)
        fwd = (cc.shift(-h) / cc - 1.0).to_numpy(dtype=float)
        ch = pd.DataFrame(cal_high)
        cl = pd.DataFrame(cal_low)
        mfe = (ch.rolling(h, min_periods=h).max().shift(-h) / cc - 1.0).to_numpy(dtype=float)
        mae = (cl.rolling(h, min_periods=h).min().shift(-h) / cc - 1.0).to_numpy(dtype=float)
        cal_fwd[h] = fwd
        cal_mfe[h] = mfe
        cal_mae[h] = mae
    print("前向面板完成 %.1fs" % (time.time() - t0))

    # ---- 逐组合回测 ----
    results = {"meta": {"period": [str(PERIOD_START), str(PERIOD_END)],
                        "n_etf": n_etf, "groups": group_list,
                        "main_combo": MAIN_COMBO,
                        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")},
               "combinations": {}}

    for combo_key in sorted(combos):
        cb = combos[combo_key]
        reb = univ_json["combinations"][combo_key]
        # 重建 rebalances（date -> reps codes）
        rebalances = []
        for r in reb.get("rebalances", []):
            rebalances.append((r["date"], [x["code"] for x in r["reps"]]))
        if not rebalances:
            # ever_in 结构（兼容）：从 ever_in 重建
            rebalances = sorted([(v["first"], [c]) for c, v in reb["ever_in"].items()])

        # in_univ[t, i] 布尔矩阵
        in_univ = np.zeros((n_days, n_etf), dtype=bool)
        code2col = {sym: j for j, sym in enumerate(syms)}
        reb_ord = np.array([date.fromisoformat(d).toordinal() for d, _ in rebalances],
                            dtype=np.int64)
        reb_idx = np.searchsorted(cal_ord, reb_ord, side="left")
        for k, (d, reps) in enumerate(rebalances):
            cols = [code2col[c] for c in reps if c in code2col]
            if not cols:
                continue
            start = reb_idx[k]
            end = reb_idx[k + 1] if k + 1 < len(reb_idx) else n_days
            if end <= start:
                continue
            in_univ[start:end, cols] = True

        # 分组基线：baseline[g][h][t]
        baseline = {g: {h: np.full(n_days, np.nan) for h in HOLDS} for g in group_list}
        for gi, g in enumerate(group_list):
            gmask = (group_id == gi)
            sel = in_univ & gmask[None, :]
            for h in HOLDS:
                fwd = cal_fwd[h]
                valid = ~np.isnan(fwd)
                num = np.where(valid, fwd, 0.0) * sel
                den = valid & sel
                nnum = num.sum(axis=1)
                dden = den.sum(axis=1)
                with np.errstate(invalid="ignore", divide="ignore"):
                    baseline[g][h] = np.where(dden > 0, nnum / dden, np.nan)

        # 不去重对照：仅流动性过滤（无相关性去重），基线 = 全部流动性达标 ETF 等权
        in_univ_liq = cal_amt60 >= cb["liq_threshold"]
        baseline_liq = {g: {h: np.full(n_days, np.nan) for h in HOLDS} for g in group_list}
        for gi, g in enumerate(group_list):
            gmask = (group_id == gi)
            sel = in_univ_liq & gmask[None, :]
            for h in HOLDS:
                fwd = cal_fwd[h]
                valid = ~np.isnan(fwd)
                num = np.where(valid, fwd, 0.0) * sel
                den = valid & sel
                with np.errstate(invalid="ignore", divide="ignore"):
                    baseline_liq[g][h] = np.where(den.sum(axis=1) > 0, num.sum(axis=1) / den.sum(axis=1), np.nan)

        # 聚合信号
        combo_result = {"liq": cb["liq_threshold"], "rho": cb["rho"], "rules": {},
                        "groups": {}}
        grp_summary = combo_result["groups"]
        for rule in ("deep30", "deep20"):
            sig = signals[rule]
            n_sig = sum(len(a) for a in sig["etf"])
            etf = np.concatenate(sig["etf"]).astype(np.int64)
            dates = np.concatenate(sig["date"]).astype(np.int64)
            qid = np.concatenate(sig["qid"]).astype(np.int64)
            cidx = np.concatenate(sig["cal_idx"]).astype(np.int64)

            # 宇宙内 + 前向有效（不跨末日）
            in_u = in_univ[cidx, etf]
            r60_sig = r60[cidx]
            rule_res = {"n_signals_total": int(n_sig), "holds": {}}
            for h in HOLDS:
                fwd = cal_fwd[h][cidx, etf]
                mfe = cal_mfe[h][cidx, etf]
                mae = cal_mae[h][cidx, etf]
                valid = in_u & np.isfinite(fwd) & np.isfinite(mfe) & np.isfinite(mae)
                # 基线
                base = np.full(etf.size, np.nan)
                for gi, g in enumerate(group_list):
                    gm = group_id[etf] == gi
                    if gm.any():
                        base[gm] = baseline[g][h][cidx[gm]]
                excess = fwd - base

                # 过滤器：dir60 down（r60 < 0）
                filt = valid & (r60_sig < 0)

                hres = {}
                for tag, mask in (("always", valid), ("filter_dir60down", filt)):
                    if not mask.any():
                        hres[tag] = {"n_signals": 0}
                        continue
                    q = qid[mask]
                    f = fwd[mask]
                    e = excess[mask]
                    mf = mfe[mask]
                    ma = mae[mask]
                    n_used = int(mask.sum())
                    # 季度聚合
                    q_abs = np.full(N_Q, np.nan)
                    q_exc = np.full(N_Q, np.nan)
                    q_win = np.full(N_Q, np.nan)  # 超额胜率（分季度）
                    for qi in range(N_Q):
                        qm = q == qi
                        if qm.any() and np.isfinite(e[qm]).any():
                            q_abs[qi] = f[qm][np.isfinite(f[qm])].mean()
                            ee = e[qm][np.isfinite(e[qm])]
                            q_exc[qi] = ee.mean()
                            q_win[qi] = (ee > 0).mean()
                    hres[tag] = {
                        "n_signals": n_used,
                        "abs_return": sign_block(q_abs),
                        "excess_return": sign_block(q_exc),
                        "excess_winrate": sign_block(q_win - 0.5),
                        "excess_mean_overall": round(float(np.nanmean(e)), 6),
                        "abs_mean_overall": round(float(np.nanmean(f)), 6),
                        "mfe_mean": round(float(np.nanmean(mf)), 6),
                        "mae_mean": round(float(np.nanmean(ma)), 6),
                        "mfe_over_abs_mae": round(float(np.nanmean(mf) / abs(np.nanmean(ma))), 6)
                        if abs(np.nanmean(ma)) > 1e-9 else None,
                        "quarter_excess": [round(float(x), 6) if np.isfinite(x) else None
                                           for x in q_exc],
                    }
                    # 分组明细（仅统计，主口径用）
                    g_sig = group_id[etf][mask]
                    for gi, g in enumerate(group_list):
                        gm = g_sig == gi
                        if not gm.any():
                            continue
                        ee = e[gm][np.isfinite(e[gm])]
                        ff = f[gm][np.isfinite(f[gm])]
                        gg = grp_summary.setdefault("%s|%d|%s" % (rule, h, tag), {})
                        gg[g] = {
                            "n": int(gm.sum()),
                            "excess_mean": round(float(ee.mean()), 6) if ee.size else None,
                            "abs_mean": round(float(ff.mean()), 6) if ff.size else None,
                            "mae_mean": round(float(np.nanmean(ma[gm])), 6),
                            "mfe_mean": round(float(np.nanmean(mf[gm])), 6),
                            "beat_rate": round(float((ee > 0).mean()), 6) if ee.size else None,
                        }
                rule_res["holds"][str(h)] = hres
            combo_result["rules"][rule] = rule_res

            # 不去重对照（仅流动性，无相关性去重）——只报 always 的 20/25/60 超额符号检验
            liq_only_res = {}
            in_u_liq = in_univ_liq[cidx, etf]
            for h in HOLDS:
                fwd = cal_fwd[h][cidx, etf]
                valid = in_u_liq & np.isfinite(fwd)
                base_liq = np.full(etf.size, np.nan)
                for gi, g in enumerate(group_list):
                    gm = group_id[etf] == gi
                    if gm.any():
                        base_liq[gm] = baseline_liq[g][h][cidx[gm]]
                excess_liq = fwd - base_liq
                m = valid & np.isfinite(excess_liq)
                if not m.any():
                    liq_only_res[str(h)] = {"n_signals": 0}
                    continue
                q = qid[m]
                e = excess_liq[m]
                q_exc = np.full(N_Q, np.nan)
                for qi in range(N_Q):
                    qm = q == qi
                    if qm.any() and np.isfinite(e[qm]).any():
                        q_exc[qi] = e[qm][np.isfinite(e[qm])].mean()
                liq_only_res[str(h)] = {"n_signals": int(m.sum()),
                                        "excess_return": sign_block(q_exc)}
            combo_result.setdefault("liq_only", {})[rule] = liq_only_res
        results["combinations"][combo_key] = combo_result
        print("  组合 %s 完成（%.1fs）" % (combo_key, time.time() - t0), flush=True)

    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n已写出 %s，总耗时 %.1fs" % (args.out, time.time() - t0))


if __name__ == "__main__":
    main()
