#!/usr/bin/env python3
"""阶段 15 偏差量化：退市截断 + 最坏情形敏感性。

## 要回答的两个问题

1. **前向收益被截断了多少**：深水单针信号在 t+h 超出该股数据末尾时会被丢弃。
   分两种原因：
   - **A 类（有偏，让结果偏乐观）**：该股在 2020-01~2026-08 期间停止更新（退市 / 长期停牌），
     它退市前那段的下跌被整段丢掉；
   - **B 类（良性）**：该股仍在交易，只是 t+h 越过了全局数据末日 2026-08-28。
2. **最坏情形敏感性**：把 A 类被丢弃的信号按「退市整理期再跌 X%」补回来
   （ret = 最后可得收盘/买入价 × (1-X) − 1，X = 50% / 80%），重算 25 日逐季度超额与符号检验，
   看结论方向是否会翻。

用法：
    .venv/bin/python scripts/stage15_bias_check.py --adjust forward --universe hs
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

from datasource.tdx.reader import parse_day_file, resolve_hsjday_root, resolve_symbol_path
from market.adjust import forward_adjust_frame

from scripts.analyze_stage15 import binom_test_two_sided, cell_to_q, safe_div
from scripts.run_stage15 import (
    LONG_DEEP_MAX,
    MIN_HIST_BARS,
    MIN_N_QUARTER,
    N_Q,
    PERIOD_END,
    PERIOD_START,
    Q_LABELS,
    SHORT_PIN,
    list_stock_symbols,
    quarter_ids,
)
from scripts.pin30_common import pin30_series

HOLD = 25
SHOCKS = (0.5, 0.8)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adjust", choices=("forward", "none"), default="forward")
    ap.add_argument("--universe", choices=("hs", "all"), default="hs")
    ap.add_argument("--base", default="data/stage15_forward_hs.json")
    ap.add_argument("--out", default="data/stage15_bias_check.json")
    args = ap.parse_args()

    root = resolve_hsjday_root()
    files = list_stock_symbols(root, args.universe)
    start_ord, end_ord = PERIOD_START.toordinal(), PERIOD_END.toordinal()

    n_sig_total = 0
    n_sig_dropped_A = 0
    n_sig_dropped_B = 0
    n_sig_kept = 0
    n_sig_from_stopped = 0
    # A 类被丢弃信号：按季度累加「最后可得收盘 / 买入价 − 1」
    dropA_n = np.zeros(N_Q)
    dropA_sum_raw = np.zeros(N_Q)          # 不加额外冲击（= 只算到停牌前最后价）
    dropA_sum_shock = {s: np.zeros(N_Q) for s in SHOCKS}
    dropA_win_shock = {s: np.zeros(N_Q) for s in SHOCKS}
    dropA_win_raw = np.zeros(N_Q)
    n_stopped_syms = 0

    for code, nbars, first, last in files:
        stopped = 20200101 <= last <= 20260801
        try:
            df = parse_day_file(resolve_symbol_path(root, code))
        except FileNotFoundError:
            continue
        if len(df) < MIN_HIST_BARS + 1:
            continue
        if args.adjust == "forward":
            df = forward_adjust_frame(df, code)
        n = len(df)
        s = pin30_series(df)
        close, short, long_, trend = s["close"], s["short"], s["long"], s["trend"]
        ords = np.fromiter((d.toordinal() for d in df["date"]), dtype=np.int64, count=n)
        i0 = max(int(np.searchsorted(ords, start_ord, "left")), MIN_HIST_BARS)
        i1 = int(np.searchsorted(ords, end_ord, "right"))
        if i1 - i0 < 1:
            continue
        idx = np.arange(i0, i1, dtype=np.int64)
        m = (~trend[idx]) & (short[idx] <= SHORT_PIN) & (long_[idx] <= LONG_DEEP_MAX) & (close[idx] > 0)
        sig = idx[m]
        if sig.size == 0:
            continue
        if stopped:
            n_stopped_syms += 1
            n_sig_from_stopped += int(sig.size)
        n_sig_total += int(sig.size)
        okh = (sig + HOLD) < n
        n_sig_kept += int(okh.sum())
        drop = sig[~okh]
        if drop.size:
            if stopped:
                n_sig_dropped_A += int(drop.size)
                qid = quarter_ids(ords[drop])
                ok = (qid >= 0) & (qid < N_Q)
                qid = qid[ok]
                base = close[drop[ok]]
                last_c = close[n - 1]
                raw = last_c / base - 1.0
                dropA_n += np.bincount(qid, minlength=N_Q)
                dropA_sum_raw += np.bincount(qid, weights=raw, minlength=N_Q)
                dropA_win_raw += np.bincount(qid, weights=(raw > 0).astype(float), minlength=N_Q)
                for sh in SHOCKS:
                    r = last_c * (1 - sh) / base - 1.0
                    dropA_sum_shock[sh] += np.bincount(qid, weights=r, minlength=N_Q)
                    dropA_win_shock[sh] += np.bincount(
                        qid, weights=(r > 0).astype(float), minlength=N_Q)
            else:
                n_sig_dropped_B += int(drop.size)
        del df

    print("=" * 110)
    print("阶段 15 偏差量化（%s / %s，持有 %d 日）" % (args.adjust, args.universe, HOLD))
    print("=" * 110)
    print("深水单针信号总数（2020-01 ~ 2026-08，含无法计算前向收益的）：%d" % n_sig_total)
    print("  纳入统计（t+%d 有价）             ：%d（%.3f%%）" % (
        HOLD, n_sig_kept, 100.0 * n_sig_kept / n_sig_total))
    print("  A 类丢弃（该股期间内停止更新）      ：%d（%.3f%%）← 有偏，方向=偏乐观" % (
        n_sig_dropped_A, 100.0 * n_sig_dropped_A / n_sig_total))
    print("  B 类丢弃（仍在交易，越过数据末日）   ：%d（%.3f%%）← 良性" % (
        n_sig_dropped_B, 100.0 * n_sig_dropped_B / n_sig_total))
    print("  来自「期间内停止更新」股票的信号     ：%d（%.3f%%），涉及 %d 只股票" % (
        n_sig_from_stopped, 100.0 * n_sig_from_stopped / n_sig_total, n_stopped_syms))

    # 把 A 类信号按最坏情形补回，重算 25 日逐季度超额
    base = json.loads(Path(args.base).read_text(encoding="utf-8"))["state"]
    r = base["rule"]["deep30"][str(HOLD)]
    b = base["base"][str(HOLD)]
    rn, rw, rs = cell_to_q(r["n"]), cell_to_q(r["win"]), cell_to_q(r["sum_ret"])
    bn, bs = cell_to_q(b["n"]), cell_to_q(b["sum_ret"])
    bar = safe_div(bs, bn)
    ex0 = safe_div(rs, rn) - bar

    print("\n%-8s %9s %9s %10s %10s %10s %10s" % (
        "季度", "原n", "补回A类n", "原超额%", "补回(不冲击)", "补回(-50%)", "补回(-80%)"))
    rows = {}
    variants = {"raw": (dropA_sum_raw, dropA_win_raw)}
    for sh in SHOCKS:
        variants["shock%d" % int(sh * 100)] = (dropA_sum_shock[sh], dropA_win_shock[sh])
    ex_new = {k: safe_div(rs + v[0], rn + dropA_n) - bar for k, v in variants.items()}
    for qi, lab in enumerate(Q_LABELS):
        rows[lab] = {
            "n": int(rn[qi]), "dropA_n": int(dropA_n[qi]),
            "excess": None if not np.isfinite(ex0[qi]) else round(float(ex0[qi]), 6),
            **{k: (None if not np.isfinite(v[qi]) else round(float(v[qi]), 6))
               for k, v in ex_new.items()},
        }
        print("%-8s %9d %9d %10.2f %12.2f %10.2f %10.2f" % (
            lab, rn[qi], dropA_n[qi], ex0[qi] * 100,
            ex_new["raw"][qi] * 100, ex_new["shock50"][qi] * 100, ex_new["shock80"][qi] * 100))

    print("\n符号检验对比（n>=%d 的季度）：" % MIN_N_QUARTER)
    summary = {}
    for tag, arr in (("原口径", ex0), ("补回A类(不冲击)", ex_new["raw"]),
                     ("补回A类(-50%)", ex_new["shock50"]), ("补回A类(-80%)", ex_new["shock80"])):
        k = np.isfinite(arr) & (rn >= MIN_N_QUARTER)
        v = arr[k]
        pos = int((v > 0).sum())
        p = binom_test_two_sided(pos, len(v))
        summary[tag] = {"n_quarters": len(v), "n_positive": pos, "p": round(p, 6),
                        "mean": round(float(v.mean()), 6), "median": round(float(np.median(v)), 6)}
        print("  %-18s 正%2d/%2d  p=%.4f  均值%+.2fpp  中位%+.2fpp" % (
            tag, pos, len(v), p, v.mean() * 100, np.median(v) * 100))

    out = {
        "meta": {"adjust": args.adjust, "universe": args.universe, "hold": HOLD},
        "counts": {
            "signals_total": n_sig_total, "kept": n_sig_kept,
            "dropped_A_stopped": n_sig_dropped_A, "dropped_B_dataend": n_sig_dropped_B,
            "signals_from_stopped_symbols": n_sig_from_stopped,
            "n_stopped_symbols_with_signals": n_stopped_syms,
        },
        "per_quarter": rows,
        "sign_test_summary": summary,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n已写入 %s" % args.out)


if __name__ == "__main__":
    main()
