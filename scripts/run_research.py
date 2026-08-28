#!/usr/bin/env python3
"""因子研究 CLI：复现 /tmp 下四个因子实验脚本（A/B/C/D 四组发现）。

用法（仓库根目录）：

    .venv/bin/python scripts/run_research.py --start 2026-03-01 --end 2026-08-27 --sample 700

输出四组面板（持有 5 日，抽样 700 只，种子 7，与 /tmp 实验同口径）：

    A. 量比基准窗口对比（5/20/60 日，分档超额）
    B. MACD 状态 × 量能交叉矩阵（水下多头 + vr60<0.6 为最强组合）
    C. 均线多头因子（5/13/25/75/120）+ 与 vr60 极缩量 / 水下多头交叉
    D. 市场环境（regime）分层：趋势跟随 vs 均值回归组合超额

数据源：本地 hsjday（只读）。完整方法论见 docs/因子研究报告.md 与
docs/市场环境模块说明.md。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datasource.tdx import parse_day_file, resolve_hsjday_root
from market.regime import compute_market_series
from research.dataset import build_factor_dataset
from research.factors import cross_excess, excess_boolean, excess_by_bins
from research.regime import layered_excess

# 股票代码前缀（与 /tmp 实验一致，只保留 A股个股）
STOCK_PREFIXES = ("60", "00", "30", "68")

# 量比分档
_VR_BINS = [0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5, 2.0, 3.0, 99]
_VR_LABELS = ["<0.5", "0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0",
              "1.0-1.2", "1.2-1.5", "1.5-2.0", "2.0-3.0", ">3.0"]

# regime 分档
_R20_BINS = [-9, -0.10, -0.04, 0.0, 0.04, 0.10, 9]
_R20_LABELS = ["强跌<-10%", "弱跌-10~-4%", "微跌-4~0", "微涨0~4%", "上涨4~10%", "强涨>10%"]
_ACT_BINS = [0, 0.8, 1.0, 1.2, 1.5, 9]
_ACT_LABELS = ["清淡<0.8", "偏淡0.8-1.0", "正常1.0-1.2", "活跃1.2-1.5", "火爆>1.5"]
_DD_BINS = [-9, -0.25, -0.15, -0.08, -0.03, 0.01]
_DD_LABELS = ["深跌<-25%", "中跌-25~-15%", "浅跌-15~-8%", "近高-8~-3%", "新高区-3~0"]


def load_stock_candles(sample: int, seed: int) -> dict:
    """抽样加载个股全量日线（与 /tmp 实验同口径：rglob + 前缀过滤 + 随机抽样）。"""
    root = resolve_hsjday_root()
    files = [p for p in root.rglob("*.day") if p.stem[2:].startswith(STOCK_PREFIXES)]
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


def _fmt_pp(x) -> str:
    return "—" if x is None or pd.isna(x) else f"{x * 100:+.2f}pp"


def _fmt_pct(x) -> str:
    return "—" if x is None or pd.isna(x) else f"{x * 100:+.2f}%"


def _print_bins(title: str, g: pd.DataFrame) -> None:
    print(f"\n── {title} ──")
    print(f"  {'档位':<14}{'n':>8}{'胜率':>8}{'超额':>9}{'均收益':>9}")
    for _, r in g.iterrows():
        if r["n"] < 500:
            continue
        print(
            f"  {str(r['label']):<14}{int(r['n']):>8}{r['win_rate']*100:>7.2f}%"
            f"{_fmt_pp(r['excess_win_rate']):>9}{_fmt_pct(r['avg_return']):>9}"
        )


def panel_volume(frame: pd.DataFrame) -> None:
    print(f"样本 {len(frame):,} 条，持有 5 日，基线胜率 {(frame['ret'] > 0).mean()*100:.2f}%")
    for col in ("vr5", "vr20", "vr60"):
        g = excess_by_bins(frame, col, _VR_BINS, _VR_LABELS)
        _print_bins(f"量比基准 {col[2:]} 日（{col}）", g)


def panel_macd_volume(frame: pd.DataFrame) -> None:
    base = (frame["ret"] > 0).mean()
    print(f"\n样本 {len(frame):,} 条，基线胜率 {base*100:.2f}%")
    combos = [
        ("水上 + 多头", frame["above"] & frame["gold"]),
        ("水上 + 空头", frame["above"] & ~frame["gold"]),
        ("水下 + 多头", ~frame["above"] & frame["gold"]),
        ("水下 + 空头", ~frame["above"] & ~frame["gold"]),
        ("水下金叉当日", ~frame["above"] & frame["cross"]),
        ("水上金叉当日", frame["above"] & frame["cross"]),
    ]
    for title, mask in combos:
        sub = frame[mask]
        if len(sub) < 300:
            continue
        print(f"\n【{title}】 n={len(sub):,} 整体超额 {((sub['ret'] > 0).mean() - base)*100:+.2f}pp")
        g = excess_by_bins(sub, "vr60", [0, 0.6, 0.9, 1.2, 99], ["极缩<0.6", "偏缩0.6-0.9", "温和0.9-1.2", "放量>1.2"])
        for _, r in g.iterrows():
            if r["n"] < 200:
                continue
            print(
                f"    {str(r['label']):<14} n={int(r['n']):>6}  超额 {_fmt_pp(r['excess_win_rate'])}  均收益 {_fmt_pct(r['avg_return'])}"
            )


def panel_ma(frame: pd.DataFrame) -> None:
    base = (frame["ret"] > 0).mean()
    print(f"\n样本 {len(frame):,} 条，基线胜率 {base*100:.2f}%")
    print("== 单因子（5/13/25/75/120）==")
    factors = [
        ("完美多头 5>13>25>75>120", frame["perfect"]),
        ("短期多头 5>13>25", frame["short_bull"]),
        ("站上 MA120", frame["above120"]),
        ("跌破 MA120", ~frame["above120"]),
        ("中期多头 MA25>MA75", frame["mid_bull"]),
    ]
    for label, mask in factors:
        r = excess_boolean(frame, mask.to_numpy(), label)
        if r["n"] < 300:
            continue
        print(
            f"  {label:<28} n={r['n']:>6}  超额 {_fmt_pp(r['excess_win_rate'])}  均收益 {_fmt_pct(r['avg_return'])}"
        )
    print("== 偏离度 (close-MA5)/MA5 ==")
    for lo, hi in [(-99, -0.08), (-0.08, -0.04), (-0.04, -0.02), (-0.02, 0), (0, 0.02), (0.02, 0.04), (0.04, 0.08), (0.08, 99)]:
        mask = (frame["dev5"] > lo) & (frame["dev5"] <= hi)
        r = excess_boolean(frame, mask.to_numpy(), f"{lo:+.2f}~{hi:+.2f}")
        if r["n"] < 300:
            continue
        print(f"  偏离 {r['label']:<12} n={r['n']:>6}  超额 {_fmt_pp(r['excess_win_rate'])}  均收益 {_fmt_pct(r['avg_return'])}")
    print("== 三因子：水下多头 × 均线 × 极缩量 ==")
    bb = frame["below_bull"]
    for label, mask in [
        ("水下多头 + 极缩量", bb & (frame["vr60"] < 0.6)),
        ("+ 站上MA120", bb & (frame["vr60"] < 0.6) & frame["above120"]),
        ("+ 短期多头", bb & (frame["vr60"] < 0.6) & frame["short_bull"]),
        ("+ 完美多头", bb & (frame["vr60"] < 0.6) & frame["perfect"]),
        ("+ 中期多头", bb & (frame["vr60"] < 0.6) & frame["mid_bull"]),
    ]:
        r = excess_boolean(frame, mask.to_numpy(), label)
        if r["n"] < 300:
            continue
        print(f"  {label:<24} n={r['n']:>6}  超额 {_fmt_pp(r['excess_win_rate'])}  均收益 {_fmt_pct(r['avg_return'])}")


def panel_regime(frame: pd.DataFrame, series: pd.DataFrame) -> None:
    # 把市场环境三指标按日期合并进因子长表（series 索引名为 date）
    ms = series[["r20", "drawdown", "activity"]].reset_index()
    merged = frame.merge(ms, on="date", how="left")
    merged = merged.dropna(subset=["r20", "drawdown", "activity"])
    base = (merged["ret"] > 0).mean()
    print(f"\n样本 {len(merged):,} 条，全区间基线胜率 {base*100:.2f}%")

    tf = merged["above"] & merged["perfect"] & merged["above120"]
    mr = merged["below_bull"] & (merged["vr60"] < 0.6)

    for name, col, bins, labels in [
        ("大盘 20 日涨跌", "r20", _R20_BINS, _R20_LABELS),
        ("距 120 日高点回撤", "drawdown", _DD_BINS, _DD_LABELS),
        ("市场活跃度(量/60均)", "activity", _ACT_BINS, _ACT_LABELS),
    ]:
        out = layered_excess(merged, col, bins, labels, tf.to_numpy(), mr.to_numpy())
        print(f"\n===== 按 {name} 分档")
        print(f"{'档位':<16}{'区间基线':>9}{'趋势跟随超额':>13}{'(n)':>8}{'均值回归超额':>13}{'(n)':>8}")
        for _, r in out.iterrows():
            t = f"{r['trend_excess']*100:+.2f}pp" if not pd.isna(r["trend_excess"]) else "样本不足"
            rev = f"{r['reversion_excess']*100:+.2f}pp" if not pd.isna(r["reversion_excess"]) else "样本不足"
            print(
                f"{str(r['label']):<16}{r['baseline_win_rate']*100:>8.2f}%{t:>13}{int(r['trend_n']):>8}"
                f"{rev:>13}{int(r['reversion_n']):>8}"
            )


def _row_to_bin(row: dict, factor: str) -> dict:
    """把 factors.excess 行转成 ResearchSummary.single_factors 的行。"""
    return {
        "factor": factor,
        "label": str(row["label"]),
        "n": int(row["n"]),
        "win_rate": round(float(row["win_rate"]), 6),
        "avg_return": round(float(row["avg_return"]), 6),
        "excess_win_rate": (
            round(float(row["excess_win_rate"]), 6)
            if row["excess_win_rate"] is not None and not pd.isna(row["excess_win_rate"])
            else None
        ),
        "excess_return": (
            round(float(row["excess_return"]), 6)
            if row["excess_return"] is not None and not pd.isna(row["excess_return"])
            else None
        ),
    }


def collect_snapshot(frame: pd.DataFrame, frame_d: pd.DataFrame, series: pd.DataFrame) -> dict:
    """把 A/B/C/D 四组面板整理成 ResearchSummary 结构（供 --out 落盘）。"""
    base = (frame["ret"] > 0).mean()
    single_factors: list[dict] = []

    # A：vr5/vr20/vr60 分档
    for col in ("vr5", "vr20", "vr60"):
        g = excess_by_bins(frame, col, _VR_BINS, _VR_LABELS)
        for _, r in g.iterrows():
            single_factors.append(_row_to_bin(r.to_dict(), col))

    # C：均线布尔因子
    ma_factors = [
        ("完美多头", frame["perfect"]),
        ("短期多头", frame["short_bull"]),
        ("站上MA120", frame["above120"]),
        ("跌破MA120", ~frame["above120"]),
        ("中期多头", frame["mid_bull"]),
    ]
    for name, mask in ma_factors:
        r = excess_boolean(frame, mask.to_numpy(), name)
        if r["n"] < 300:
            continue
        single_factors.append(
            {
                "factor": name,
                "label": name,
                "n": r["n"],
                "win_rate": round(r["win_rate"], 6),
                "avg_return": round(r["avg_return"], 6),
                "excess_win_rate": round(r["excess_win_rate"], 6),
                "excess_return": round(r["excess_return"], 6),
            }
        )

    # B：MACD 状态 × vr60 交叉矩阵
    cross_matrix: list[dict] = []
    state_cols = [
        ("水上多头", frame["above"] & frame["gold"]),
        ("水上空头", frame["above"] & ~frame["gold"]),
        ("水下多头", ~frame["above"] & frame["gold"]),
        ("水下空头", ~frame["above"] & ~frame["gold"]),
    ]
    vol_bins = [0, 0.6, 0.9, 1.2, 99]
    vol_labels = ["极缩<0.6", "偏缩0.6-0.9", "温和0.9-1.2", "放量>1.2"]
    for state_name, mask in state_cols:
        sub = frame[mask]
        g = excess_by_bins(sub, "vr60", vol_bins, vol_labels)
        for _, r in g.iterrows():
            cross_matrix.append(
                {
                    "row": state_name,
                    "col": str(r["label"]),
                    "n": int(r["n"]),
                    "win_rate": round(float(r["win_rate"]), 6),
                    "excess_win_rate": (
                        round(float(r["excess_win_rate"]), 6)
                        if not pd.isna(r["excess_win_rate"])
                        else None
                    ),
                }
            )

    # D：regime 分层
    ms = series[["r20", "drawdown", "activity"]].reset_index()
    merged = frame_d.merge(ms, on="date", how="left").dropna(
        subset=["r20", "drawdown", "activity"]
    )
    tf = merged["above"] & merged["perfect"] & merged["above120"]
    mr = merged["below_bull"] & (merged["vr60"] < 0.6)
    regime_layers: list[dict] = []
    for dim, col, bins, labels in [
        ("大盘 20 日涨跌", "r20", _R20_BINS, _R20_LABELS),
        ("距 120 日高点回撤", "drawdown", _DD_BINS, _DD_LABELS),
        ("市场活跃度", "activity", _ACT_BINS, _ACT_LABELS),
    ]:
        out = layered_excess(merged, col, bins, labels, tf.to_numpy(), mr.to_numpy())
        for _, r in out.iterrows():
            regime_layers.append(
                {
                    "dimension": dim,
                    "label": str(r["label"]),
                    "baseline_win_rate": round(float(r["baseline_win_rate"]), 6),
                    "trend_n": int(r["trend_n"]),
                    "trend_excess": (
                        round(float(r["trend_excess"]), 6)
                        if not pd.isna(r["trend_excess"])
                        else None
                    ),
                    "reversion_n": int(r["reversion_n"]),
                    "reversion_excess": (
                        round(float(r["reversion_excess"]), 6)
                        if not pd.isna(r["reversion_excess"])
                        else None
                    ),
                }
            )

    return {
        "as_of": str(frame["date"].max()),
        "sample": int(frame["symbol"].nunique()),
        "hold_days": 5,
        "baseline_win_rate": round(float(base), 6),
        "single_factors": single_factors,
        "cross_matrix": cross_matrix,
        "regime_layers": regime_layers,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="因子研究 CLI")
    parser.add_argument("--start", default="2026-03-01")
    parser.add_argument("--end", default="2026-08-27")
    parser.add_argument("--sample", type=int, default=700)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--hold", type=int, default=5)
    parser.add_argument("--regime-start", default="2023-01-01", help="regime 面板的起始日（更长样本）")
    parser.add_argument("--out", default=None, help="可选：结构化快照 JSON 输出路径（ResearchSummary）")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    regime_start = date.fromisoformat(args.regime_start)

    print(f"加载个股样本（sample={args.sample}, seed={args.seed}）...", flush=True)
    candles = load_stock_candles(args.sample, args.seed)
    print(f"  已加载 {len(candles)} 只，构建因子数据集...", flush=True)

    frame = build_factor_dataset(candles, start, end, hold_days=args.hold)
    if frame.empty:
        print("因子数据集为空，请检查 hsjday 数据路径或日期区间")
        return

    print("=" * 90)
    print("【A】量比基准窗口对比（5/20/60 日）")
    panel_volume(frame)

    print("\n" + "=" * 90)
    print("【B】MACD 状态 × 量能（vr60）交叉矩阵")
    panel_macd_volume(frame)

    print("\n" + "=" * 90)
    print("【C】均线多头因子（5/13/25/75/120）")
    panel_ma(frame)

    print("\n" + "=" * 90)
    print("【D】市场环境（regime）分层：趋势跟随 vs 均值回归")
    series = compute_market_series(candles)
    if series.empty:
        print("市场序列为空（样本广度不足），跳过 regime 面板")
        return
    # regime 面板用更长样本（覆盖 2023-01 起）
    frame_d = build_factor_dataset(candles, regime_start, end, hold_days=args.hold)
    panel_regime(frame_d, series)

    if args.out:
        snapshot = collect_snapshot(frame, frame_d, series)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结构化快照已写入 {out}")


if __name__ == "__main__":
    main()
