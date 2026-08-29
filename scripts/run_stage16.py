#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 16：把「事后分档」的互补性变成「实时可执行」——信号日当天可算的市场状态分流验证。

背景（见 docs/阶段15-报告.md §2）：深水单针（deep30）在弱势市场为正、原始单针（orig）
在强势市场为正，两者互补。但那个分档用的是**季度实际涨跌幅**（事后信息，实盘不可用）。

本脚本要回答：**用信号日当天及之前就能算出来的市场状态，能否复现同样的互补性？**

候选环境指标（全部只用信号日 t 及更早的数据，严禁前视）：
  1. 大盘（沪深300）滚动 60 日涨跌幅，三分档
  2. 大盘滚动 20 日涨跌幅，三分档（对照阶段 11 的失败口径）
  3. 大盘价格 vs MA60 / MA120 的位置（上方/下方，二值）
  4. 大盘滚动 60 日涨跌幅的方向（上升/下降，二值）
  5. 上涨股票占比（市场宽度，滚动 20 日均值），三分档

对每个候选：按该指标把 27 个季度的**信号（不是季度）**分档，分别算 deep30 与 orig
在各档的 20/25/60 日超额（信号收益 − 同季度同持有期基线）。判定哪个候选能让
「deep30 弱势档为正、orig 强势档为正」成立。

然后构造分流规则：环境判强势 → 用 orig；判弱势 → 用 deep30，回测 vs 单用其一 vs
全市场基线，按 27 个季度做符号检验。

诚实条款：5 个候选全试、全部披露（多重比较）。找不到能复现的指标就照实说。

用法：
    PYTHONPATH="packages/..." python3 scripts/run_stage16.py --adjust forward \
        --out data/stage16_market_state.json
"""
from __future__ import annotations

import argparse
import gc
import json
import math
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
from strategies.filters import SymbolKind, classify_symbol, filter_for_kinds, kind_excluded
from scripts.pin30_common import pin30_series

PERIOD_START = date(2020, 1, 1)
PERIOD_END = date(2026, 8, 28)
HOLDS = (20, 25, 60)
SHORT_PIN = 30.0
LONG_DEEP_MAX = 55.0
LONG_ORIG_MIN = 80.0
MIN_HIST_BARS = 120
INDEX_HS300 = "sh000300"
INDEX_SSE = "sh000001"


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
Q_LABELS = [q["label"] for q in QUARTERS]
_Q_START_ORD = np.array([q["start"].toordinal() for q in QUARTERS], dtype=np.int64)


def quarter_ids(ordinals: np.ndarray) -> np.ndarray:
    return np.searchsorted(_Q_START_ORD, ordinals, side="right") - 1


def list_stock_symbols(root: Path, universe: str) -> list[str]:
    cfg = filter_for_kinds((SymbolKind.STOCK,))
    markets = ("sh", "sz") if universe == "hs" else ("sh", "sz", "bj")
    out = []
    for market in markets:
        lday = root / market / "lday"
        if not lday.is_dir():
            continue
        for fn in sorted(lday.iterdir()):
            if not fn.name.endswith(".day"):
                continue
            code = fn.name[2:8]
            if len(code) != 6:
                continue
            if kind_excluded(classify_symbol(market, code), cfg):
                continue
            out.append(code)
    return out


def load_index(root: Path, code: str) -> pd.Series:
    market = "sh" if code.startswith("sh") else "sz"
    df = parse_day_file(root / market / "lday" / ("%s.day" % code))
    return df.set_index("date")["close"].astype(float)


def build_market_state(root: Path, cal: np.ndarray) -> dict:
    hs = load_index(root, INDEX_HS300)
    cal_dates = [date.fromordinal(int(o)) for o in cal]
    close = hs.reindex(cal_dates).ffill().to_numpy(dtype=float)

    n = len(cal)
    r20 = np.full(n, np.nan)
    r60 = np.full(n, np.nan)
    ma60 = np.full(n, np.nan)
    ma120 = np.full(n, np.nan)
    for i in range(n):
        if i >= 20:
            r20[i] = close[i] / close[i - 20] - 1.0
        if i >= 60:
            r60[i] = close[i] / close[i - 60] - 1.0
        if i >= 59:
            ma60[i] = close[i - 59 : i + 1].mean()
        if i >= 119:
            ma120[i] = close[i - 119 : i + 1].mean()

    return {
        "cal": cal,
        "close": close,
        "r20": r20,
        "r60": r60,
        "ma60": ma60,
        "ma120": ma120,
        "above_ma60": np.where(np.isnan(ma60), np.nan, (close > ma60).astype(float)),
        "above_ma120": np.where(np.isnan(ma120), np.nan, (close > ma120).astype(float)),
        "dir60": np.where(np.isnan(r60), np.nan, (r60 > 0).astype(float)),
    }


def run_scan(args, mkt: dict) -> dict:
    root = resolve_hsjday_root()
    cal = mkt["cal"]
    ncal = len(cal)
    cal_minus1 = np.concatenate(([np.iinfo(np.int64).min], cal[:-1]))

    breadth_num = np.zeros(ncal, dtype=np.float64)
    breadth_den = np.zeros(ncal, dtype=np.float64)

    symbols = list_stock_symbols(root, args.universe)
    if args.limit:
        symbols = symbols[: args.limit]

    cols = ("date", "qid", "ret20", "ret25", "ret60")
    sig = {"deep30": {k: [] for k in cols}, "orig": {k: [] for k in cols}}

    start_ord = PERIOD_START.toordinal()
    end_ord = PERIOD_END.toordinal()
    t0 = time.time()

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
        short = s["short"]
        long_ = s["long"]
        trend = s["trend"]

        ordinals = np.fromiter((d.toordinal() for d in df["date"]), dtype=np.int64, count=n)
        i0 = int(np.searchsorted(ordinals, start_ord, side="left"))
        i1 = int(np.searchsorted(ordinals, end_ord, side="right"))
        i0 = max(i0, MIN_HIST_BARS)
        if i1 - i0 < 1:
            continue

        idx = np.arange(i0, i1, dtype=np.int64)
        ords = ordinals[i0:i1]
        qid = quarter_ids(ords)

        # 市场宽度：本股在 t 与 t-1 都是连续交易日时，是否上涨
        pos = np.searchsorted(cal, ords, side="left")
        pos_c = np.clip(pos, 0, ncal - 1)
        inb = (pos >= 0) & (pos < ncal) & (cal[pos_c] == ords)
        prev_ok = np.zeros(len(pos), dtype=bool)
        if inb.any():
            prev_ok[inb] = cal_minus1[pos[inb]] == ordinals[i0 - 1 : i1 - 1][inb]
        adv = (close[i0:i1] > close[i0 - 1 : i1 - 1]) & prev_ok
        pidx = pos[inb]
        np.add.at(breadth_num, pidx, adv[inb].astype(np.float64))
        np.add.at(breadth_den, pidx, prev_ok[inb].astype(np.float64))

        not_trend = ~trend[idx]
        m_deep30 = not_trend & (short[idx] <= SHORT_PIN) & (long_[idx] <= LONG_DEEP_MAX)
        m_orig = trend[idx] & (short[idx] <= SHORT_PIN) & (long_[idx] >= LONG_ORIG_MIN)
        masks = {"deep30": m_deep30, "orig": m_orig}

        for rule, m in masks.items():
            if not m.any():
                continue
            si = idx[m]
            sig[rule]["date"].append(ordinals[si])
            sig[rule]["qid"].append(qid[m])
            for h in HOLDS:
                ok = (si + h) < n
                r = np.full(si.size, np.nan)
                r[ok] = close[si[ok] + h] / close[si[ok]] - 1.0
                sig[rule]["ret%d" % h].append(r)

        if (i + 1) % 1000 == 0:
            print("  ...%d/%d 只，%.0fs" % (i + 1, len(symbols), time.time() - t0), flush=True)
            gc.collect()

    sigs = {r: {k: np.concatenate(sig[r][k]) for k in cols} for r in ("deep30", "orig")}
    den = np.where(breadth_den > 0, breadth_den, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        daily_adv = np.where(breadth_den > 0, breadth_num / breadth_den, np.nan)
    br = pd.Series(daily_adv).rolling(20, min_periods=1).mean().to_numpy(dtype=float)
    return {"meta": {"adjust": args.adjust, "universe": args.universe,
                     "n_symbols": len(symbols),
                     "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")},
            "signals": sigs, "breadth20": br}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adjust", choices=("forward", "none"), default="forward")
    ap.add_argument("--universe", choices=("hs", "all"), default="hs")
    ap.add_argument("--out", default="data/stage16_market_state.json")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--skip-scan", action="store_true")
    args = ap.parse_args()

    root = resolve_hsjday_root()
    sse = load_index(root, INDEX_SSE)
    ords_all = np.array([d.toordinal() for d in sse.index], dtype=np.int64)
    lo, hi = PERIOD_START.toordinal(), PERIOD_END.toordinal()
    cal = ords_all[(ords_all >= lo) & (ords_all <= hi)]
    mkt = build_market_state(root, cal)
    print("交易日历 %d 天" % len(cal))

    cache = Path("data/stage16_signals_cache.json")
    if args.skip_scan and cache.exists():
        raw = json.loads(cache.read_text())
        scan = {"meta": raw["meta"],
                "signals": {r: {k: np.asarray(v) for k, v in raw["signals"][r].items()}
                            for r in ("deep30", "orig")},
                "breadth20": np.asarray(raw["breadth20"])}
        print("从缓存加载信号")
    else:
        scan = run_scan(args, mkt)
        cache.write_text(json.dumps(
            {"meta": scan["meta"],
             "signals": {r: {k: v.tolist() for k, v in scan["signals"][r].items()}
                         for r in ("deep30", "orig")},
             "breadth20": scan["breadth20"].tolist()}, ensure_ascii=False))
        print("信号缓存已写 %s" % cache)

    st15 = json.loads((ROOT / "data" / "stage15_analysis.json").read_text())
    base_avg = {h: np.array(st15["quarter_table_deep30"][str(h)]["base_avg_return"], dtype=float)
                for h in HOLDS}
    ref_excess = {h: np.array(st15["quarter_table_deep30"][str(h)]["excess_return"], dtype=float)
                  for h in HOLDS}

    analyze(mkt, scan, base_avg, ref_excess, args.out)


def analyze(mkt, scan, base_avg, ref_excess, out_path) -> None:
    cal = mkt["cal"]
    ncal = len(cal)
    sigs = scan["signals"]

    def cal_pos(dates):
        return np.clip(np.searchsorted(cal, dates, side="left"), 0, ncal - 1)

    def tercile_bounds(vals):
        v = vals[np.isfinite(vals)]
        return float(np.quantile(v, 1 / 3)), float(np.quantile(v, 2 / 3))

    indicators = {}
    for key, series, name in (
        ("r60_tercile", mkt["r60"], "大盘滚动60日涨跌幅三分档"),
        ("r20_tercile", mkt["r20"], "大盘滚动20日涨跌幅三分档"),
    ):
        lo_, hi_ = tercile_bounds(series)
        indicators[key] = {"name": name, "kind": "tercile", "series": series, "bounds": (lo_, hi_)}

    br20 = np.asarray(scan["breadth20"], dtype=float)
    lo_b, hi_b = tercile_bounds(br20)
    indicators["breadth20_tercile"] = {"name": "市场宽度(滚动20日均)三分档", "kind": "tercile",
                                       "series": br20, "bounds": (lo_b, hi_b)}

    indicators["above_ma60"] = {"name": "大盘收盘 vs MA60（上/下）", "kind": "binary",
                                "series": mkt["above_ma60"].astype(float)}
    indicators["above_ma120"] = {"name": "大盘收盘 vs MA120（上/下）", "kind": "binary",
                                 "series": mkt["above_ma120"].astype(float)}
    indicators["dir60"] = {"name": "大盘滚动60日涨跌幅方向（升/降）", "kind": "binary",
                           "series": mkt["dir60"].astype(float)}

    result = {"meta": scan["meta"], "indicators": {}, "split_backtest": {},
              "equivalence_check": {}, "always": {}}

    # 等价性校验
    eq = {}
    for h in HOLDS:
        d = sigs["deep30"]
        ret = d["ret%d" % h]
        qid = d["qid"]
        exc = ret - base_avg[h][qid]
        ok = np.isfinite(exc)
        qmean = np.full(N_Q, np.nan)
        for q in range(N_Q):
            m = ok & (qid == q)
            if m.any():
                qmean[q] = exc[m].mean()
        ref = ref_excess[h]
        both = np.isfinite(qmean) & np.isfinite(ref)
        corr = float(np.corrcoef(qmean[both], ref[both])[0, 1]) if both.sum() > 2 else None
        mae = float(np.mean(np.abs(qmean[both] - ref[both]))) if both.any() else None
        eq[h] = {"n_signals": int(ok.sum()), "corr_with_stage15": corr,
                 "mean_abs_diff": mae}
        print("等价校验 hold=%d: 信号 %d，与阶段15 季度超额相关系数 %.4f，平均绝对差 %.4f%%" % (
            h, eq[h]["n_signals"], corr, (mae * 100) if mae is not None else float("nan")))
    result["equivalence_check"] = eq

    # 始终 deep30 / 始终 orig（信号日粒度）
    for rule in ("deep30", "orig"):
        d = sigs[rule]
        qid = d["qid"]
        res = {}
        for h in HOLDS:
            exc = d["ret%d" % h] - base_avg[h][qid]
            ok = np.isfinite(exc)
            qmean = np.full(N_Q, np.nan)
            for q in range(N_Q):
                m = ok & (qid == q)
                if m.any():
                    qmean[q] = exc[m].mean()
            res[h] = sign_block(qmean)
        result["always"][rule] = res

    # 主分析
    for key, ind in indicators.items():
        series = ind["series"]
        pos_d = cal_pos(sigs["deep30"]["date"])
        pos_o = cal_pos(sigs["orig"]["date"])
        qid_d = sigs["deep30"]["qid"]
        qid_o = sigs["orig"]["qid"]

        if ind["kind"] == "tercile":
            lo_, hi_ = ind["bounds"]
            t_d = np.where(series[pos_d] < lo_, 0, np.where(series[pos_d] <= hi_, 1, 2))
            t_o = np.where(series[pos_o] < lo_, 0, np.where(series[pos_o] <= hi_, 1, 2))
            t_d[np.isnan(series[pos_d])] = -1
            t_o[np.isnan(series[pos_o])] = -1
            tier_names = {0: "weak", 1: "mid", 2: "strong"}
        else:
            t_d = np.where(series[pos_d] == 1, 2, 0)
            t_o = np.where(series[pos_o] == 1, 2, 0)
            t_d[np.isnan(series[pos_d])] = -1
            t_o[np.isnan(series[pos_o])] = -1
            tier_names = {0: "weak", 2: "strong"}

        ind_res = {"name": ind["name"], "kind": ind["kind"],
                   "bounds": ind.get("bounds"), "tiers": {}}
        for rule, t, qid, d in (("deep30", t_d, qid_d, sigs["deep30"]),
                                ("orig", t_o, qid_o, sigs["orig"])):
            for ti, tname in tier_names.items():
                sel = t == ti
                row = {"n_signals": int(sel.sum())}
                for h in HOLDS:
                    exc = d["ret%d" % h] - base_avg[h][qid]
                    m = sel & np.isfinite(exc)
                    row["excess_%d" % h] = float(exc[m].mean()) if m.any() else None
                    row["beat_base_%d" % h] = float((exc[m] > 0).mean()) if m.any() else None
                ind_res["tiers"].setdefault(tname, {})[rule] = row
        result["indicators"][key] = ind_res

        # 互补性判定
        comp = {}
        for h in HOLDS:
            wd = ind_res["tiers"].get("weak", {}).get("deep30", {}).get("excess_%d" % h)
            so = ind_res["tiers"].get("strong", {}).get("orig", {}).get("excess_%d" % h)
            comp[h] = {"deep30_weak": wd, "orig_strong": so,
                       "complementary": (wd is not None and so is not None and wd > 0 and so > 0)}
        ind_res["complementarity"] = comp

        # 分流回测：强势档 → orig，其余（weak+mid）→ deep30
        sel_d = t_d != 2
        sel_d &= t_d != -1
        sel_o = t_o == 2
        split = {}
        for h in HOLDS:
            exc_d = sigs["deep30"]["ret%d" % h][sel_d] - base_avg[h][qid_d[sel_d]]
            exc_o = sigs["orig"]["ret%d" % h][sel_o] - base_avg[h][qid_o[sel_o]]
            qd = qid_d[sel_d]
            qo = qid_o[sel_o]
            qmean = np.full(N_Q, np.nan)
            n_used = np.zeros(N_Q, dtype=int)
            for q in range(N_Q):
                a = np.isfinite(exc_d) & (qd == q)
                b = np.isfinite(exc_o) & (qo == q)
                vals = np.concatenate([exc_d[a], exc_o[b]]) if (a.any() or b.any()) else np.array([])
                if vals.size:
                    qmean[q] = vals.mean()
                    n_used[q] = int(vals.size)
            split[h] = sign_block(qmean)
            split[h]["n_used"] = n_used.tolist()
            split[h]["n_quarters_used"] = int(np.isfinite(qmean).sum())
        result["split_backtest"][key] = split

        # 对照：只过滤 deep30（弱势档→deep30，强势档→空仓，不用 orig）
        filt = {}
        for h in HOLDS:
            exc_d = sigs["deep30"]["ret%d" % h][sel_d] - base_avg[h][qid_d[sel_d]]
            qd = qid_d[sel_d]
            qmean = np.full(N_Q, np.nan)
            for q in range(N_Q):
                a = np.isfinite(exc_d) & (qd == q)
                if a.any():
                    qmean[q] = exc_d[a].mean()
            filt[h] = sign_block(qmean)
        result["split_backtest"][key + "__deep30_filter_only"] = filt

    Path(out_path).write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print("\n已写出 %s" % out_path)


def sign_block(qmean) -> dict:
    v = qmean[np.isfinite(qmean)]
    n = len(v)
    k = int((v > 0).sum())
    return {"n_quarters": n, "n_positive": k, "p_binom": round(binom_two_sided(k, n), 6),
            "mean": round(float(v.mean()), 6) if n else None,
            "median": round(float(np.median(v)), 6) if n else None,
            "sum": round(float(v.sum()), 6) if n else None}


if __name__ == "__main__":
    main()
