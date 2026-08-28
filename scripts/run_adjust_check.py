#!/usr/bin/env python3
"""复权因子接入：样本内关键结论在「未复权 vs 前复权」下的变化（阶段 9 跨阶段遗留）。

背景：hsjday 为不复权原始数据，除权除息日会在 K 线留下「假跌幅」，回测若不处理
会把除权当成真实暴跌。本脚本用 market.adjust 的启发式除权检测 + 前复权换算，
重跑 docs/因子研究报告.md 的样本内四组发现，量化「复权修正后结论变化多少」。

用法（仓库根目录）：
    .venv/bin/python scripts/run_adjust_check.py --out data/adjust_check.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from market.adjust import detect_ex_rights, forward_adjust_frame, limit_down_pct
from research.dataset import build_factor_dataset
from run_oos_factors import evaluate_findings, load_candles


def count_ex_rights(candles: dict, start: date, end: date) -> dict:
    """统计每只标的在区间内（含前推回看）的除权日数。"""
    total = 0
    affected = 0
    in_window = 0
    for symbol, df in candles.items():
        closes = df["close"].astype(float).to_numpy()
        ex = detect_ex_rights(closes, limit_down_pct(symbol))
        n = int(ex.sum())
        if n > 0:
            affected += 1
            total += n
        if "date" in df.columns:
            dates = df["date"].to_numpy()
            mask = np.asarray([start <= d <= end for d in dates])
            in_window += int(np.asarray(ex[mask]).sum())
    return {"affected_symbols": affected, "total_events": total, "events_in_window": in_window}


def main() -> None:
    parser = argparse.ArgumentParser(description="复权因子接入检查")
    parser.add_argument("--sample", type=int, default=700)
    parser.add_argument("--out", default="data/adjust_check.json")
    args = parser.parse_args()

    start = date(2026, 3, 1)
    end = date(2026, 8, 27)

    print("加载个股样本（%d 只）..." % args.sample, flush=True)
    raw = load_candles(args.sample, 7)
    print("  已加载 %d 只" % len(raw), flush=True)

    stats = count_ex_rights(raw, start, end)
    print("  除权事件：%d 只标的发生过（共 %d 次），其中样本内区间 %d 次"
          % (stats["affected_symbols"], stats["total_events"], stats["events_in_window"]), flush=True)

    # 前复权 candles
    adj = {s: forward_adjust_frame(df, s) for s, df in raw.items()}

    print("构建因子数据集（未复权 vs 前复权）...", flush=True)
    frame_raw = build_factor_dataset(raw, start, end, hold_days=5)
    frame_adj = build_factor_dataset(adj, start, end, hold_days=5)
    print("  未复权 %d 条 / 前复权 %d 条" % (len(frame_raw), len(frame_adj)), flush=True)

    r_raw = evaluate_findings(frame_raw)
    r_adj = evaluate_findings(frame_adj)

    _print_delta(r_raw, r_adj, stats)

    out = {"stats": stats, "raw": r_raw, "adjusted": r_adj}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("\n结构化快照已写入 %s" % args.out)


def _pp(x):
    return "—" if x is None else ("%+.2fpp" % x)


def _print_delta(raw: dict, adj: dict, stats: dict) -> None:
    print("\n" + "=" * 90)
    print("样本内关键结论：未复权 vs 前复权")
    print("=" * 90)
    print("基线胜率：未复权 %.2f%% → 前复权 %.2f%%"
          % (raw["baseline_win_rate"] * 100, adj["baseline_win_rate"] * 100))

    print("\n[F1 量比基准 vr60]")
    for key in ("low_<0.6", "high_>3.0"):
        a = raw["f1_volume_ratio"]["vr60"][key]
        b = adj["f1_volume_ratio"]["vr60"][key]
        print("  %-10s 未复权 %s → 前复权 %s" % (key, _pp(a), _pp(b)))

    print("\n[F2 MACD×量能 below_bull 极缩<0.6]")
    a = raw["f2_macd_volume"]["below_bull"]["cells"]["极缩<0.6"]["excess"]
    b = adj["f2_macd_volume"]["below_bull"]["cells"]["极缩<0.6"]["excess"]
    print("  未复权 %s → 前复权 %s" % (_pp(a), _pp(b)))

    print("\n[F3 均线多头]")
    for name in ("perfect", "short_bull", "above120", "below120", "mid_bull"):
        a = raw["f3_ma_bull"][name]["excess"]
        b = adj["f3_ma_bull"][name]["excess"]
        print("  %-12s 未复权 %s → 前复权 %s" % (name, _pp(a), _pp(b)))

    print("\n[F4 偏离度两端]")
    for lab in ("低端<-8%", "-8~-4%", "-2~0", "4~8%", "高端>8%"):
        a = raw["f4_deviation"][lab]["excess"]
        b = adj["f4_deviation"][lab]["excess"]
        print("  %-10s 未复权 %s → 前复权 %s" % (lab, _pp(a), _pp(b)))


if __name__ == "__main__":
    main()
