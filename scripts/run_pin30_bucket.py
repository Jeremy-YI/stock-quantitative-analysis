#!/usr/bin/env python3
"""pin30 单针下30 按趋势状态分桶重测（阶段 12 任务 1）。

## 问题

阶段 10 测的 pin30 四段 20 日超额 -2.1/+2.1/+0.8/+1.2 ≈ 0，是把整个策略
（原始 pin30 信号 + b1_w 信号）混着测的。本脚本把「单针下30」这个**基础事件**
（短期随机 <= 30）按趋势状态 + 长期随机位置分四桶，看原始口径（桶1）是否真的
有正超额、以及「深水单针」（桶3）这个加仓候选是否真的可做。

## 分桶口径（严格按需求，不做参数搜索）

基础事件 = 短期随机 <= 30（short = (C-LLV(L,3))/(HHV(C,3)-LLV(L,3)+eps)*100）。

    - 桶1 趋势多头 + 长期>=80       （原始 pin30，上升趋势洗盘）
    - 桶2 趋势多头 + 长期 50~80     （上升趋势中段回踩）
    - 桶3 非趋势多头 + 长期<=55     （深水，下跌趋势）
    - 桶4 其余

另测「深水变体」：非趋势多头 + 长期<=55 + 短期<=20（更深的单针，Jeremy 口径
「跌破 30 或 20」里的 20 档）。

趋势多头 = ST_RAW > LT_RAW 且 C > LT_RAW（ST_RAW=EMA(EMA(C,10),10)，
LT_RAW=(MA14+MA28+MA57+MA114)/4）。全部复刻 strategies.pin30.strategy。

## 持有期与基线

持有期 5/10/20/40/60 五个交易日。收益 = close[i+H]/close[i]-1（与 backtest.forward
同式）。基线 = backtest.baseline.compute_baseline 同期同宇宙（个股）「随机持有 N 日」，
每个持有期分别做差。数据截止窗口结束日，窗口最后 H 个交易日的信号无 H 日收益，
会被排除在 n 之外（与基线同口径，超额对比公平）。

用法（仓库根目录）：
    .venv/bin/python scripts/run_pin30_bucket.py --windows IS A B C \
        --out data/pin30_bucket.json
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
from strategies.filters import SymbolKind
from strategies.pin30.config import default_config as pin30_default_config

from scripts.pin30_common import BUCKET_NAMES, bucket_of, pin30_series
from scripts.run_oos_strategies import WINDOW_LABELS, WINDOWS, load_universe, peak_rss_mb

HOLDS = [5, 10, 20, 40, 60]
SHORT_THRESHOLD = 30.0
DEEP_SHORT_THRESHOLD = 20.0
MIN_N = 100  # 样本量红线：低于此值标注「样本不足，不作结论」
WARMUP_BARS = 320  # 覆盖 MA114 + EMA(10,10) + 长随机(20) + 缓冲

BUCKETS = [1, 2, 3, 4]


def _stats(rets: list[float], base_win: float, base_ret: float, signals: int) -> dict:
    """把一段收益列表折成统计（绝对 + 超额）。"""
    arr = np.asarray(rets, dtype=float) if rets else np.empty(0)
    n = int(arr.size)
    win = float((arr > 0).mean()) if n else 0.0
    avg = float(arr.mean()) if n else 0.0
    return {
        "signals": signals,
        "n": n,
        "win_rate": round(win, 6),
        "avg_return": round(avg, 6),
        "excess_win_rate": round(win - base_win, 6),
        "excess_return": round(avg - base_ret, 6),
        "insufficient": n < MIN_N,
    }


def run_window(window: str) -> dict:
    label = WINDOW_LABELS[window]
    start, end = (date.fromisoformat(x) for x in WINDOWS[window])
    days = _trading_days_in_window(window)
    lookback = len(days) + WARMUP_BARS
    print("\n" + "=" * 80)
    print("【%s】%s ~ %s（%d 交易日，回看 %d 根）" % (label, start, end, len(days), lookback))

    t0 = time.time()
    candles, kind_map = load_universe(end, lookback, kinds=(SymbolKind.STOCK,), verbose=True)
    print("  加载个股 %d 只，%.1fs，RSS峰值 %.0fMB" % (len(candles), time.time() - t0, peak_rss_mb()))

    symbols = sorted(candles)
    start_ord = start.toordinal()
    end_ord = end.toordinal()
    cfg = pin30_default_config()
    min_bars = cfg.min_bars

    # 分桶累计：fwd[b][h] = 收益列表；deep20[h] = 深水变体收益列表
    fwd: dict[int, dict[int, list]] = {b: {h: [] for h in HOLDS} for b in BUCKETS}
    sig: dict[int, int] = {b: 0 for b in BUCKETS}
    deep20_fwd: dict[int, list] = {h: [] for h in HOLDS}
    deep20_sig = 0

    t0 = time.time()
    for si, symbol in enumerate(symbols, 1):
        df = candles[symbol]
        n = len(df)
        if n < min_bars:
            continue
        s = pin30_series(df)
        dates = df["date"].to_numpy()
        ordinals = np.array([d.toordinal() for d in dates], dtype=np.int64)
        closes = s["close"]
        short = s["short"]
        long_ = s["long"]
        trend = s["trend"]

        i0 = int(np.searchsorted(ordinals, start_ord, side="left"))
        i1 = int(np.searchsorted(ordinals, end_ord, side="right"))
        for i in range(i0, i1):
            if i + 1 < min_bars:
                continue
            if short[i] > SHORT_THRESHOLD:
                continue
            b = bucket_of(bool(trend[i]), float(long_[i]))
            sig[b] += 1
            # 前向收益
            for h in HOLDS:
                j = i + h
                if j < n and closes[i] > 0:
                    fwd[b][h].append(closes[j] / closes[i] - 1.0)
            # 深水变体：非趋势 + 长期<=55 + 短期<=20
            if b == 3 and short[i] <= DEEP_SHORT_THRESHOLD:
                deep20_sig += 1
                for h in HOLDS:
                    j = i + h
                    if j < n and closes[i] > 0:
                        deep20_fwd[h].append(closes[j] / closes[i] - 1.0)

        if si % 2000 == 0:
            gc.collect()
            print("    ...%d/%d 只，%.1fs，RSS峰值 %.0fMB" % (si, len(symbols), time.time() - t0, peak_rss_mb()), flush=True)

    print("  扫描完成，%.1fs" % (time.time() - t0))

    # 基线（个股宇宙，同持有期）
    base = compute_baseline(candles, symbols, "stock", start, end, HOLDS)
    baselines = {str(h.hold_days): {"win_rate": h.win_rate, "avg_return": h.avg_return, "n": h.n} for h in base.holds}

    result: dict = {"window": label, "start": str(start), "end": str(end), "universe_size": len(symbols)}
    result["baselines"] = baselines
    result["buckets"] = {}
    for b in BUCKETS:
        entry = {"name": BUCKET_NAMES[b], "signals": sig[b], "holds": {}}
        for h in HOLDS:
            entry["holds"][str(h)] = _stats(
                fwd[b][h], baselines[str(h)]["win_rate"], baselines[str(h)]["avg_return"], sig[b]
            )
        result["buckets"][str(b)] = entry
    result["deep20"] = {
        "name": "深水变体 非趋势多头+长期<=55+短期<=20",
        "signals": deep20_sig,
        "holds": {
            str(h): _stats(deep20_fwd[h], baselines[str(h)]["win_rate"], baselines[str(h)]["avg_return"], deep20_sig)
            for h in HOLDS
        },
    }

    # 释放大对象
    del candles
    gc.collect()
    return result


def _trading_days_in_window(window: str) -> list[date]:
    from market.calendar import trading_days

    start, end = (date.fromisoformat(x) for x in WINDOWS[window])
    return trading_days(start, end)


def _bucket_rows(results: dict) -> list[tuple[str, str]]:
    """(key, name) 顺序表：四桶 + 深水变体。"""
    first = results[[l for l in ("IS", "OOS-A", "OOS-B", "OOS-C") if l in results][0]]
    rows = [(b, first["buckets"][b]["name"]) for b in ("1", "2", "3", "4")]
    rows.append(("deep20", first["deep20"]["name"]))
    return rows


def print_report(results: dict) -> None:
    labels = [l for l in ("IS", "OOS-A", "OOS-B", "OOS-C") if l in results]
    rows = _bucket_rows(results)
    print("\n" + "=" * 112)
    print("pin30 单针下30 分桶：超额胜率（pp）/ 超额收益（%%）（* = 样本量 < %d）" % MIN_N)
    print("=" * 112)
    for h in HOLDS:
        print("\n  —— 持有 %d 日 ——" % h)
        hdr = "    %-42s" % "桶"
        for l in labels:
            hdr += "%22s" % l
        print(hdr)
        for key, name in rows:
            row = "    %-42s" % name
            for l in labels:
                src = results[l]["buckets"] if key != "deep20" else {"deep20": results[l]["deep20"]}
                cell = src[key]["holds"][str(h)]
                mark = "*" if cell["insufficient"] else " "
                row += "%22s" % (
                    "%s%+.1f / %+.2f / %d"
                    % (mark, cell["excess_win_rate"] * 100, cell["excess_return"] * 100, cell["n"])
                )
            print(row)
        # 基线与绝对收益（供对照）
        bl = "    %-42s" % "[基线 胜率%/均值%]"
        for l in labels:
            b = results[l]["baselines"][str(h)]
            bl += "%22s" % ("%.1f / %+.2f" % (b["win_rate"] * 100, b["avg_return"] * 100))
        print(bl)


def main() -> None:
    ap = argparse.ArgumentParser(description="pin30 单针下30 分桶重测")
    ap.add_argument("--windows", nargs="+", default=["IS", "A", "B", "C"])
    ap.add_argument("--out", default="data/pin30_bucket.json")
    args = ap.parse_args()

    out_path = Path(args.out)
    results: dict = {}
    if out_path.exists():
        try:
            results = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            results = {}

    for window in args.windows:
        results[WINDOW_LABELS[window]] = run_window(window)
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print_report(results)
    print("\n结构化快照已写入 %s" % out_path)


if __name__ == "__main__":
    main()
