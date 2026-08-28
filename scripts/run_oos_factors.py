#!/usr/bin/env python3
"""样本外（OOS）因子验证：把 docs/因子研究报告.md 的四组核心发现在三段 OOS 区间重跑。

回答的核心问题（阶段 9 最高优先级）：阶段 8 的因子结论全部来自 2026-03~08 单区间，
是典型样本内拟合；本脚本把四组发现逐条在样本内 + 三段样本外区间重跑，判定哪些稳健、
哪些是拟合噪声。

区间定义（与任务书一致）：
    IS     2026-03-01 ~ 2026-08-27   （现有全部结论的来源，样本内）
    OOS-A  2023-01-01 ~ 2023-12-31
    OOS-B  2024-01-01 ~ 2024-12-31
    OOS-C  2025-01-01 ~ 2026-02-28

四组发现（复现口径与 run_research.py 完全一致，sample=700 / seed=7 / 持有 5 日）：
    F1  量比基准窗口：vr60 是否仍单调（越缩量越好 / 越放量越差）、vr5 是否仍反向
    F2  MACD 水下多头 × vr60<0.6 是否仍是交叉矩阵最强格
    F3  均线多头因子（5/13/25/75/120）是否仍全部负超额
    F4  偏离度 (close-MA5)/MA5 是否仍呈 U 形（两端正超额 / 中间负超额）

用法（仓库根目录）：
    .venv/bin/python scripts/run_oos_factors.py [--sample 700] [--out data/oos_factors.json]

数据源：本地 hsjday（只读）。每个窗口约 1~2 分钟（700 只抽样，向量化）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from research.dataset import build_factor_dataset
from research.factors import excess_boolean, excess_by_bins

# 样本内 + 三段样本外区间（含标签）
WINDOWS: list[tuple[str, str, str]] = [
    ("IS", "2026-03-01", "2026-08-27"),
    ("OOS-A", "2023-01-01", "2023-12-31"),
    ("OOS-B", "2024-01-01", "2024-12-31"),
    ("OOS-C", "2025-01-01", "2026-02-28"),
]

# 量比分档（与 docs/因子研究报告.md §2 的高层桶一致：<0.6 / 0.6-0.9 / 0.9-1.0 /
# 1.0-1.2 / 1.2-1.5 / 1.5-3.0 / >3.0）。headline 用 <0.6 与 >3.0 两个端点桶。
_VR_BINS = [0, 0.6, 0.9, 1.0, 1.2, 1.5, 3.0, 99]
_VR_LABELS = ["<0.6", "0.6-0.9", "0.9-1.0", "1.0-1.2", "1.2-1.5", "1.5-3.0", ">3.0"]


def load_candles(sample: int, seed: int) -> dict:
    """抽样加载个股全量日线（与 run_research.load_stock_candles 同口径）。"""
    from datasource.tdx import parse_day_file, resolve_hsjday_root
    import random

    root = resolve_hsjday_root()
    files = [p for p in root.rglob("*.day") if p.stem[2:].startswith(("60", "00", "30", "68"))]
    random.Random(seed).shuffle(files)
    picked = files[: min(sample, len(files))]
    candles: dict = {}
    for p in picked:
        try:
            df = parse_day_file(p)
        except Exception:
            continue
        if df is not None and len(df) >= 130:
            candles[p.stem[2:8]] = df
    return candles


def _pp(x) -> float | None:
    """把小数超额转成百分点数值（None/NaN → None）。"""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if pd.isna(f):
        return None
    return round(f * 100, 2)


def evaluate_findings(frame: pd.DataFrame) -> dict:
    """对单个窗口的因子长表算四组发现的量化指标（纯函数）。"""
    if frame.empty:
        return {}
    base = float((frame["ret"] > 0).mean())
    out: dict = {"n": int(len(frame)), "baseline_win_rate": round(base, 4)}

    # F1：量比基准窗口单调性（vr5 / vr20 / vr60 的 <0.6 档与 >3.0 档超额）
    #     超额 = 分档胜率 − 全样本基线胜率（与 docs §2 同口径）。
    f1: dict = {}
    for col in ("vr5", "vr20", "vr60"):
        g = excess_by_bins(frame, col, _VR_BINS, _VR_LABELS)
        m = {str(r["label"]): float(r["excess_win_rate"]) for _, r in g.iterrows()}
        f1[col] = {
            "low_<0.6": _pp(m.get("<0.6")),
            "high_>3.0": _pp(m.get(">3.0")),
            "all_bins": {k: _pp(v) for k, v in m.items()},
        }
    out["f1_volume_ratio"] = f1

    # F2：MACD 状态 × vr60 交叉矩阵。headline = 各状态 vr60<0.6 格的胜率 − 全样本基线
    #     （与 docs §3 的 +9.39pp 同口径：不是相对该状态自身基线的超额）。
    states = {
        "above_bull": frame["above"] & frame["gold"],
        "above_bear": frame["above"] & ~frame["gold"],
        "below_bull": frame["below_bull"],
        "below_bear": ~frame["above"] & ~frame["gold"],
    }
    vol_bins = [0, 0.6, 0.9, 1.2, 99]
    vol_labels = ["极缩<0.6", "偏缩0.6-0.9", "温和0.9-1.2", "放量>1.2"]
    f2: dict = {}
    for name, mask in states.items():
        sub = frame[mask]
        cells: dict = {}
        for lo, hi, lab in zip(vol_bins[:-1], vol_bins[1:], vol_labels):
            sel = sub[(sub["vr60"] > lo) & (sub["vr60"] <= hi)]
            n = int(len(sel))
            if n == 0:
                cells[lab] = {"n": 0, "excess": None}
                continue
            wr = float((sel["ret"] > 0).mean())
            cells[lab] = {"n": n, "excess": _pp(wr - base)}
        f2[name] = {"n": int(len(sub)), "cells": cells}
    out["f2_macd_volume"] = f2

    # F3：均线多头因子
    factors = [
        ("perfect", frame["perfect"]),
        ("short_bull", frame["short_bull"]),
        ("above120", frame["above120"]),
        ("below120", ~frame["above120"]),
        ("mid_bull", frame["mid_bull"]),
    ]
    f3: dict = {}
    for name, mask in factors:
        r = excess_boolean(frame, mask.to_numpy(), name)
        f3[name] = {"n": r["n"], "excess": _pp(r["excess_win_rate"])}
    out["f3_ma_bull"] = f3

    # F4：偏离度 U 形
    f4: dict = {}
    for lo, hi, lab in [
        (-99, -0.08, "低端<-8%"),
        (-0.08, -0.04, "-8~-4%"),
        (-0.04, -0.02, "-4~-2%"),
        (-0.02, 0.0, "-2~0"),
        (0.0, 0.02, "0~2%"),
        (0.02, 0.04, "2~4%"),
        (0.04, 0.08, "4~8%"),
        (0.08, 99, "高端>8%"),
    ]:
        mask = (frame["dev5"] > lo) & (frame["dev5"] <= hi)
        r = excess_boolean(frame, mask.to_numpy(), lab)
        f4[lab] = {"n": r["n"], "excess": _pp(r["excess_win_rate"])}
    out["f4_deviation"] = f4
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="OOS 因子验证")
    parser.add_argument("--sample", type=int, default=700)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--hold", type=int, default=5)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    print("加载个股样本（sample=%d, seed=%d）..." % (args.sample, args.seed), flush=True)
    candles = load_candles(args.sample, args.seed)
    print("  已加载 %d 只标的" % len(candles), flush=True)

    results: dict = {}
    for label, s, e in WINDOWS:
        start = date.fromisoformat(s)
        end = date.fromisoformat(e)
        print("\n" + "=" * 80)
        print("【%s】%s ~ %s" % (label, s, e), flush=True)
        frame = build_factor_dataset(candles, start, end, hold_days=args.hold)
        if frame.empty:
            print("  因子数据集为空（区间内无足够数据），跳过")
            results[label] = {"empty": True}
            continue
        r = evaluate_findings(frame)
        results[label] = r
        _print_window(label, r)

    if args.out:
        Path(args.out).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("\n结构化快照已写入 %s" % args.out)


def _fmt(x) -> str:
    return "—" if x is None else ("%+.2fpp" % x)


def _print_window(label: str, r: dict) -> None:
    base = r.get("baseline_win_rate", 0.0) * 100
    print("  样本 %d 条，基线胜率 %.2f%%" % (r.get("n", 0), base))

    f1 = r.get("f1_volume_ratio", {})
    print("  [F1 量比基准]")
    for col, d in f1.items():
        print("    %s  <0.6 档超额 %s    >3.0 档超额 %s" % (col, _fmt(d["low_<0.6"]), _fmt(d["high_>3.0"])))

    f2 = r.get("f2_macd_volume", {})
    print("  [F2 MACD×量能 最强格]")
    for name, d in f2.items():
        cell = d["cells"].get("极缩<0.6")
        print("    %-12s n=%6d  极缩<0.6 超额 %s" % (name, d["n"], _fmt(cell["excess"])))

    f3 = r.get("f3_ma_bull", {})
    print("  [F3 均线多头]")
    for name, d in f3.items():
        print("    %-12s n=%6d  超额 %s" % (name, d["n"], _fmt(d["excess"])))

    f4 = r.get("f4_deviation", {})
    print("  [F4 偏离度 U 形]")
    for lab, d in f4.items():
        print("    %-12s n=%6d  超额 %s" % (lab, d["n"], _fmt(d["excess"])))


if __name__ == "__main__":
    main()
