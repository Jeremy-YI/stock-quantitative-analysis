#!/usr/bin/env python3
"""B1 前置条件验证：信号事后打标 + 分桶超额（阶段 10 追加需求）。

## 问题

`b1b2b3` 是「裸 B1」：只要 J<16 或 K≤30 就报信号，没有任何 MACD 位置 / 量价确认
前置条件。Jeremy 的框架里明确写着「水下金叉=诱多」「大跌区间里的第一个 B1 不能做」。
所以四段区间都测出 b1b2b3 ≈ 0 超额并不奇怪——它把「该做的 B1」和「不该做的 B1」
混在一个桶里平均掉了。本脚本不改策略、不重扫，用**事后打标 + 分桶**把它们拆开。

## 标签口径（严格按需求定义，不做参数搜索）

1. `macd_side`：日线 DIF > 0 → `above`（水上）；否则 → `below`（水下）。
2. `b1_seq`：同一段水下过程里的第几个 B1。**以 DIF 上穿零轴作为计数重置点**，
   水下期间出现的 B1 依次编号 1 / 2 / 3+。水上的 B1 不编号。
   历史起点之前就已在水下、且到信号日一直没上过水的，标 `censored`（单独统计，
   不混入 seq 桶）。
3. `drawdown_regime`（三个口径**并列**打标，输出时对比区分度）：
   - `dd120`：收盘距过去 120 日最高价（HHV(high,120)）回撤 ≤ -20%
   - `ma60_down`：MA60 斜率向下（MA60[i] < MA60[i-5]）且 收盘 < MA60
   - `index_down`：沪深300（sh000300）20 日涨跌幅 ≤ -5%
4. `vp_confirm`：vr60 ≥ 1.5 且收阳（close > open）→ `confirmed`；
   vr60 < 0.8 → `unconfirmed`；其余 → `neutral`。

## 为什么不用信号 pkl 里的 signal_type

lite 信号缓存只有 (strategy, symbol, date)，没有 b1/b2/b3 子类型；而 `b1_seq`
还需要「窗口开始之前那段水下里已经出现过几个 B1」——pkl 里根本没有窗口外的日子。
所以 B1 集合在这里**按 b1b2b3 的原始判定式（J<16 或 K≤30）向量化重算**，
并用 `--validate-days` 抽样调用策略模块自身的 `_evaluate` 逐条核对（默认 3 天），
保证重算口径与线上策略一致。

## 口径一致性

- 20 日收益 = `close[i+20] / close[i] - 1`（与 `backtest.forward.forward_returns` 同式）。
- 基线 = `backtest.baseline.compute_baseline` 的同期个股基线（与主表同一函数）。
- K 线截止窗口结束日（与 `run_oos_strategies.summarize` 一致），因此窗口最后
  20 个交易日的信号没有 20 日收益，会被排除在 n 之外。

用法：
    .venv/bin/python scripts/run_signal_labeling.py --windows IS A B C \
        --out data/signal_labels.json
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.baseline import compute_baseline
from datasource.tdx import parse_day_file, resolve_hsjday_root
from indicators.kdj import calc_kdj
from indicators.macd import calc_macd
from indicators.volume import calc_volume_ratio
from market.calendar import trading_days
from strategies import b1b2b3
from strategies.b1b2b3.config import default_config as b1_default_config
from strategies.filters import SymbolKind

from scripts.run_oos_strategies import WINDOW_LABELS, WINDOWS, load_universe, peak_rss_mb

HSJDAY = resolve_hsjday_root()
INDEX_SYMBOL = "sh000300"  # 沪深300，index_down 口径用

# 标签阈值（集中在这里，禁止散落在逻辑里；本次是分桶验证，不做阈值搜索）
DD120_WINDOW = 120
DD120_MAX = -20.0  # %
MA60_PERIOD = 60
MA60_SLOPE_LOOKBACK = 5
INDEX_RET_WINDOW = 20
INDEX_RET_MAX = -5.0  # %
VR60_CONFIRM_MIN = 1.5
VR60_UNCONFIRM_MAX = 0.8
HOLD = 20  # 头条持有期（与主表一致）
MIN_N = 100  # 样本量下限：低于此值必须标注「样本不足，不作结论」
WARMUP_BARS = 320  # 窗口开始前多留的回看根数（覆盖 vr60 / MA60 / HHV120 + 水下段计数）


# ----------------------------------------------------------------------------
# 指标序列
# ----------------------------------------------------------------------------


def _rolling_max(values: np.ndarray, window: int) -> np.ndarray:
    """滚动窗口最大值（含当日，窗口不足时用已有数据），O(n*window) 但 n 很小。"""
    out = np.empty(len(values), dtype=float)
    for i in range(len(values)):
        out[i] = values[max(0, i - window + 1) : i + 1].max()
    return out


def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    """滚动均值（含当日，窗口不足时用已有数据）。"""
    csum = np.concatenate(([0.0], np.cumsum(values)))
    out = np.empty(len(values), dtype=float)
    for i in range(len(values)):
        start = max(0, i - window + 1)
        out[i] = (csum[i + 1] - csum[start]) / (i + 1 - start)
    return out


def index_down_flags(end: date) -> dict[date, bool]:
    """沪深300 20 日涨跌幅 ≤ -5% 的日期集合（大盘「大跌区间」口径）。"""
    path = HSJDAY / "sh" / "lday" / ("%s.day" % INDEX_SYMBOL)
    df = parse_day_file(path)
    df = df[df["date"] <= end]
    closes = df["close"].astype(float).to_numpy()
    dates = df["date"].tolist()
    flags: dict[date, bool] = {}
    for i, d in enumerate(dates):
        if i < INDEX_RET_WINDOW:
            flags[d] = False
            continue
        prev = closes[i - INDEX_RET_WINDOW]
        flags[d] = bool(prev > 0 and (closes[i] / prev - 1.0) * 100.0 <= INDEX_RET_MAX)
    return flags


def label_symbol(
    df,
    window_days: set[date],
    index_flags: dict[date, bool],
) -> list[dict]:
    """对单只标的算全序列指标，返回窗口内每个 B1 日的标签行。"""
    n = len(df)
    if n < 30:
        return []
    closes_l = df["close"].astype(float).tolist()
    highs_l = df["high"].astype(float).tolist()
    lows_l = df["low"].astype(float).tolist()
    opens = df["open"].astype(float).to_numpy()
    closes = np.asarray(closes_l, dtype=float)
    highs = np.asarray(highs_l, dtype=float)
    volumes = df["volume"].astype(float).tolist()
    dates = df["date"].tolist()

    dif, _dea, _bar = calc_macd(closes_l)
    k_vals, _d_vals, j_vals = calc_kdj(highs_l, lows_l, closes_l)
    vr60 = calc_volume_ratio(volumes, period=60)
    cfg = b1_default_config()

    hhv120 = _rolling_max(highs, DD120_WINDOW)
    ma60 = _rolling_mean(closes, MA60_PERIOD)

    rows: list[dict] = []
    seq = 0
    saw_above = False
    for i in range(n):
        below = not (dif[i] > 0)
        if not below:
            saw_above = True
            seq = 0
        is_b1 = j_vals[i] < cfg.j_b1_threshold or k_vals[i] <= cfg.k_b1_threshold
        if below and is_b1:
            seq += 1
        d = dates[i]
        if d not in window_days or not is_b1:
            continue

        fwd = closes[i + HOLD] / closes[i] - 1.0 if i + HOLD < n and closes[i] > 0 else None
        dd120 = (closes[i] / hhv120[i] - 1.0) * 100.0 if hhv120[i] > 0 else 0.0
        ma60_down = bool(
            i >= MA60_SLOPE_LOOKBACK
            and ma60[i] < ma60[i - MA60_SLOPE_LOOKBACK]
            and closes[i] < ma60[i]
        )
        v = vr60[i]
        if v >= VR60_CONFIRM_MIN and closes[i] > opens[i]:
            vp = "confirmed"
        elif v < VR60_UNCONFIRM_MAX:
            vp = "unconfirmed"
        else:
            vp = "neutral"

        rows.append(
            {
                "date": d,
                "macd_side": "below" if below else "above",
                "b1_seq": seq if below else 0,
                "censored": bool(below and not saw_above),
                "dd120": bool(dd120 <= DD120_MAX),
                "ma60_down": ma60_down,
                "index_down": bool(index_flags.get(d, False)),
                "vp_confirm": vp,
                "fwd20": fwd,
            }
        )
    return rows


# ----------------------------------------------------------------------------
# 分桶
# ----------------------------------------------------------------------------


def bucket_of(row: dict) -> str | None:
    """核心四桶（需求里点名要的对照）。"""
    if row["macd_side"] == "above":
        return "水上（不分序号）"
    if row["censored"]:
        return None  # 水下段起点在历史之外，序号不可信 → 不进 seq 桶
    if row["b1_seq"] >= 2:
        return "水下 + b1_seq>=2"
    if row["b1_seq"] == 1:
        return "水下 + b1_seq=1 + %s" % {
            "confirmed": "confirmed",
            "unconfirmed": "unconfirmed",
            "neutral": "neutral",
        }[row["vp_confirm"]]
    return None


BUCKET_ORDER = [
    "水下 + b1_seq=1 + unconfirmed",
    "水下 + b1_seq=1 + confirmed",
    "水下 + b1_seq=1 + neutral",
    "水下 + b1_seq>=2",
    "水上（不分序号）",
]

# 硬性过滤规则候选（按保留哪些桶定义）。这不是参数搜索：
# 每条规则都是需求里已经点名的分桶组合，只看它们在四段区间里的表现。
FILTER_RULES: dict[str, list[str]] = {
    "R0 不过滤（全部 B1）": BUCKET_ORDER,
    "R1 只剔「水下#1 无确认」": [b for b in BUCKET_ORDER if b != "水下 + b1_seq=1 + unconfirmed"],
    "R2 只做水下（剔水上）": [b for b in BUCKET_ORDER if not b.startswith("水上")],
    "R3 水下 且 (seq>=2 或 #1+confirmed)": ["水下 + b1_seq=1 + confirmed", "水下 + b1_seq>=2"],
    "R4 只做水下 seq>=2": ["水下 + b1_seq>=2"],
}


def union_stats(buckets: dict, names: list[str], base_win: float, base_ret: float) -> dict:
    """多个桶合并后的统计（胜率/平均收益都是按 n 加权均值，可直接合并）。"""
    n = sum(buckets[b].get("n", 0) for b in names)
    sig = sum(buckets[b].get("signals", 0) for b in names)
    if n == 0:
        return {"n": 0, "signals": sig}
    win = sum(buckets[b].get("win_rate", 0.0) * buckets[b].get("n", 0) for b in names) / n
    ret = sum(buckets[b].get("avg_return", 0.0) * buckets[b].get("n", 0) for b in names) / n
    return {
        "signals": sig,
        "n": n,
        "win_rate": round(win, 6),
        "avg_return": round(ret, 6),
        "excess_win_rate": round(win - base_win, 6),
        "excess_return": round(ret - base_ret, 6),
        "insufficient": n < MIN_N,
    }


def filter_impact(window_result: dict) -> dict:
    """把分桶结果折成「硬性过滤规则」的代价/收益：砍掉多少信号、剩下的超额。"""
    buckets = window_result["buckets"]
    base_win = window_result["baseline"]["win_rate"]
    base_ret = window_result["baseline"]["avg_return"]
    total_n = sum(buckets[b].get("n", 0) for b in BUCKET_ORDER)
    out: dict = {}
    for rule, names in FILTER_RULES.items():
        s = union_stats(buckets, names, base_win, base_ret)
        s["kept_ratio"] = round(s.get("n", 0) / total_n, 6) if total_n else None
        s["cut_ratio"] = round(1 - s["kept_ratio"], 6) if s["kept_ratio"] is not None else None
        out[rule] = s
    return out


def stats(rows: list[dict], base_win: float, base_ret: float) -> dict:
    rets = [r["fwd20"] for r in rows if r["fwd20"] is not None]
    if not rets:
        return {"n": 0, "signals": len(rows)}
    arr = np.asarray(rets, dtype=float)
    win = float((arr > 0).mean())
    avg = float(arr.mean())
    return {
        "signals": len(rows),
        "n": len(rets),
        "win_rate": round(win, 6),
        "avg_return": round(avg, 6),
        "excess_win_rate": round(win - base_win, 6),
        "excess_return": round(avg - base_ret, 6),
        "insufficient": len(rets) < MIN_N,
    }


def validate_against_strategy(candles: dict, days: list[date], n_days: int) -> list[str]:
    """抽样天：向量化重算的 B1 集合必须与 b1b2b3 策略模块自身的判定完全一致。"""
    from strategies.slicing import DaySliceView, build_date_index

    if n_days <= 0:
        return []
    step = max(1, len(days) // n_days)
    probes = days[::step][:n_days]
    index, _ = build_date_index(candles)
    cfg = b1_default_config()
    problems: list[str] = []
    for day in probes:
        view = DaySliceView(candles, index, day)
        truth = {
            s.symbol
            for s in b1b2b3.scan(view, day)
            if s.signal_type == "b1"
        }
        mine: set[str] = set()
        for symbol in candles:
            df = candles[symbol]
            sub = df[df["date"] <= day]
            if len(sub) < cfg.min_bars:
                continue
            k, _d, j = calc_kdj(
                sub["high"].astype(float).tolist(),
                sub["low"].astype(float).tolist(),
                sub["close"].astype(float).tolist(),
            )
            if j[-1] < cfg.j_b1_threshold or k[-1] <= cfg.k_b1_threshold:
                mine.add(symbol)
        if mine != truth:
            problems.append(
                "%s 重算 B1 与策略不一致：重算多 %d，策略多 %d"
                % (day, len(mine - truth), len(truth - mine))
            )
        else:
            print("    校验 %s：B1 %d 只，与策略模块逐条一致 ✓" % (day, len(truth)), flush=True)
    return problems


def run_window(window: str, validate_days: int) -> dict:
    label = WINDOW_LABELS[window]
    start, end = (date.fromisoformat(x) for x in WINDOWS[window])
    days = trading_days(start, end)
    lookback = len(days) + WARMUP_BARS
    print("\n" + "=" * 80)
    print("【%s】%s ~ %s（%d 交易日，回看 %d 根）" % (label, start, end, len(days), lookback))

    t0 = time.time()
    candles, kind_map = load_universe(end, lookback, kinds=(SymbolKind.STOCK,))
    print("  加载个股 %d 只，%.1fs，RSS峰值 %.0fMB" % (len(candles), time.time() - t0, peak_rss_mb()))

    if validate_days:
        problems = validate_against_strategy(candles, days, validate_days)
        if problems:
            for p in problems:
                print("  ❌ " + p)
            raise SystemExit("B1 重算口径与策略模块不一致，中止")

    idx_flags = index_down_flags(end)
    window_days = set(days)

    t0 = time.time()
    rows: list[dict] = []
    for i, symbol in enumerate(sorted(candles)):
        rows.extend(label_symbol(candles[symbol], window_days, idx_flags))
        if (i + 1) % 2000 == 0:
            print("    打标 %d/%d，累计 B1 %d 条，%.0fs"
                  % (i + 1, len(candles), len(rows), time.time() - t0), flush=True)
    print("  B1 信号 %d 条，打标耗时 %.1fs" % (len(rows), time.time() - t0))

    bs = compute_baseline(candles, set(candles), "stock", start, end, [HOLD])
    hold = next(h for h in bs.holds if h.hold_days == HOLD)
    base_win, base_ret = hold.win_rate, hold.avg_return
    print("  个股基线（%d 日）：胜率 %.2f%%，平均收益 %+.2f%%，n=%d"
          % (HOLD, base_win * 100, base_ret * 100, hold.n))

    out: dict = {
        "window": label,
        "start": str(start),
        "end": str(end),
        "trading_days": len(days),
        "baseline": {"win_rate": base_win, "avg_return": base_ret, "n": hold.n, "size": bs.size},
        "total_b1": len(rows),
        "censored": sum(1 for r in rows if r["censored"]),
        "buckets": {},
        "regime_buckets": {},
        "seq_hist": {},
    }

    grouped: dict[str, list[dict]] = {b: [] for b in BUCKET_ORDER}
    for r in rows:
        b = bucket_of(r)
        if b is not None:
            grouped[b].append(r)
    for b in BUCKET_ORDER:
        out["buckets"][b] = stats(grouped[b], base_win, base_ret)

    # 序号分布（水下、未截断）
    hist: dict[str, int] = {}
    for r in rows:
        if r["macd_side"] == "below" and not r["censored"]:
            key = "3+" if r["b1_seq"] >= 3 else str(r["b1_seq"])
            hist[key] = hist.get(key, 0) + 1
    out["seq_hist"] = dict(sorted(hist.items()))

    # 三个 drawdown_regime 口径各切一次
    for regime in ("dd120", "ma60_down", "index_down"):
        cell: dict = {}
        for b in BUCKET_ORDER:
            inside = [r for r in grouped[b] if r[regime]]
            outside = [r for r in grouped[b] if not r[regime]]
            cell[b] = {
                "in_regime": stats(inside, base_win, base_ret),
                "out_regime": stats(outside, base_win, base_ret),
            }
        out["regime_buckets"][regime] = cell

    del candles, kind_map, rows, grouped
    gc.collect()
    return out


def _fmt(s: dict, field: str, scale: float = 100.0, sign: bool = True) -> str:
    if not s or s.get("n", 0) == 0 or s.get(field) is None:
        return "—"
    v = s[field] * scale
    txt = ("%+.1f" if sign else "%.1f") % v
    return txt + ("*" if s.get("insufficient") else "")


def print_report(results: dict) -> None:
    labels = [l for l in ("IS", "OOS-A", "OOS-B", "OOS-C") if l in results]
    print("\n" + "=" * 108)
    print("B1 前置条件：分桶 20 日超额对照（* = 样本量 < %d，样本不足不作结论）" % MIN_N)
    print("=" * 108)
    for title, field in (("20 日超额胜率（pp）", "excess_win_rate"),
                         ("20 日超额收益（%）", "excess_return"),
                         ("样本量 n", "n")):
        print("\n  %s：" % title)
        hdr = "    %-32s" % "桶"
        for l in labels:
            hdr += "%12s" % l
        print(hdr)
        for b in BUCKET_ORDER:
            row = "    %-32s" % b
            for l in labels:
                s = results[l]["buckets"].get(b, {})
                if field == "n":
                    row += "%12s" % (s.get("n", 0))
                else:
                    row += "%12s" % _fmt(s, field)
            print(row)

    print("\n  水下 B1 序号分布（未截断样本）：")
    for l in labels:
        print("    %-8s %s（censored %d / 全部 B1 %d）"
              % (l, results[l]["seq_hist"], results[l]["censored"], results[l]["total_b1"]))

    for regime in ("dd120", "ma60_down", "index_down"):
        print("\n  【%s】区间内 vs 区间外（20 日超额胜率 pp / 超额收益 %% / n）：" % regime)
        hdr = "    %-32s" % "桶"
        for l in labels:
            hdr += "%26s" % l
        print(hdr)
        for b in BUCKET_ORDER:
            row = "    %-32s" % b
            for l in labels:
                cell = results[l]["regime_buckets"][regime][b]
                row += "%26s" % (
                    "%s/%s/%d vs %s/%s/%d"
                    % (
                        _fmt(cell["in_regime"], "excess_win_rate"),
                        _fmt(cell["in_regime"], "excess_return"),
                        cell["in_regime"].get("n", 0),
                        _fmt(cell["out_regime"], "excess_win_rate"),
                        _fmt(cell["out_regime"], "excess_return"),
                        cell["out_regime"].get("n", 0),
                    )
                )
            print(row)

    print("\n  硬性过滤规则的代价/收益（保留比例 | 20 日超额胜率 pp | 超额收益 %）：")
    hdr = "    %-34s" % "规则"
    for l in labels:
        hdr += "%24s" % l
    print(hdr)
    for rule in FILTER_RULES:
        row = "    %-34s" % rule
        for l in labels:
            s = results[l].get("filter_impact", {}).get(rule, {})
            row += "%24s" % (
                "%.0f%% | %s | %s"
                % (
                    (s.get("kept_ratio") or 0) * 100,
                    _fmt(s, "excess_win_rate"),
                    _fmt(s, "excess_return"),
                )
            )
        print(row)


def main() -> None:
    ap = argparse.ArgumentParser(description="B1 前置条件：事后打标 + 分桶超额")
    ap.add_argument("--windows", nargs="+", default=["IS", "A", "B", "C"])
    ap.add_argument("--validate-days", type=int, default=3,
                    help="抽样多少天与 b1b2b3 策略模块逐条核对 B1 集合（0=跳过）")
    ap.add_argument("--out", default="data/signal_labels.json")
    ap.add_argument("--report-only", action="store_true",
                    help="不重跑打标，只从已有 JSON 重算派生块（过滤规则影响）并重打印报表")
    args = ap.parse_args()

    out_path = Path(args.out)
    results: dict = {}
    if out_path.exists():
        try:
            results = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            results = {}

    for window in ([] if args.report_only else args.windows):
        res = run_window(window, args.validate_days)
        results[res["window"]] = res
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    order = ["IS", "OOS-A", "OOS-B", "OOS-C"]
    results = {k: results[k] for k in order if k in results}
    for k in results:
        results[k]["filter_impact"] = filter_impact(results[k])
    print_report(results)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n结构化快照已写入 %s（RSS峰值 %.0fMB）" % (out_path, peak_rss_mb()))


if __name__ == "__main__":
    main()
