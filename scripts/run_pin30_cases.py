#!/usr/bin/env python3
"""pin30 单针下30 信号明细：三只点名股 + 医药生物板块（阶段 12 任务 3）。

对指定 watchlist 逐日算单针下30（短期随机 <= 30）事件，输出每条信号的分桶标签、
信号日收盘价（= 加仓点位）、以及 5/10/20/40/60 日前向收益，供人工复核。

watchlist：
    - 点名股：600206 有研新材 / 600522 中天科技 / 601398 工商银行
    - 医药生物（东财 BK1216）：sector_members.json 里的 509 只成分

用法（仓库根目录）：
    .venv/bin/python scripts/run_pin30_cases.py --windows IS A B C \
        --out data/pin30_cases.json
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

from strategies.filters import SymbolKind
from strategies.pin30.config import default_config as pin30_default_config

from scripts.pin30_common import BUCKET_NAMES, bucket_of, pin30_series
from scripts.run_oos_strategies import WINDOW_LABELS, WINDOWS, load_universe, peak_rss_mb

HOLDS = [5, 10, 20, 40, 60]
SHORT_THRESHOLD = 30.0
WARMUP_BARS = 320

NAMED = {
    "600206": "有研新材",
    "600522": "中天科技",
    "601398": "工商银行",
}


def load_medical_codes() -> dict[str, str]:
    d = json.loads((ROOT / "data" / "sector_members.json").read_text(encoding="utf-8"))
    sec = d["sectors"]["BK1216"]  # 医药生物
    return {m["code"]: m["name"] for m in sec["members"]}


def run_window(window: str, watch: dict[str, str]) -> dict:
    label = WINDOW_LABELS[window]
    start, end = (date.fromisoformat(x) for x in WINDOWS[window])
    from market.calendar import trading_days

    days = trading_days(start, end)
    lookback = len(days) + WARMUP_BARS
    print("\n" + "=" * 80)
    print("【%s】%s ~ %s（watchlist %d 只）" % (label, start, end, len(watch)))

    t0 = time.time()
    symbols = sorted(watch)
    candles, _kind_map = load_universe(end, lookback, kinds=(SymbolKind.STOCK,), verbose=False)
    print("  加载宇宙 %d 只，%.1fs（只处理 watchlist %d 只）" % (len(candles), time.time() - t0, len(symbols)))

    start_ord = start.toordinal()
    end_ord = end.toordinal()
    cfg = pin30_default_config()
    min_bars = cfg.min_bars

    result: dict = {"window": label, "start": str(start), "end": str(end), "stocks": {}}
    for symbol in symbols:
        df = candles.get(symbol)
        if df is None or len(df) < min_bars:
            continue
        s = pin30_series(df)
        n = len(df)
        dates = df["date"].to_numpy()
        ordinals = np.array([d.toordinal() for d in dates], dtype=np.int64)
        closes = s["close"]
        short = s["short"]
        long_ = s["long"]
        trend = s["trend"]

        i0 = int(np.searchsorted(ordinals, start_ord, side="left"))
        i1 = int(np.searchsorted(ordinals, end_ord, side="right"))
        rows = []
        for i in range(i0, i1):
            if i + 1 < min_bars:
                continue
            if short[i] > SHORT_THRESHOLD:
                continue
            b = bucket_of(bool(trend[i]), float(long_[i]))
            fwd = {}
            for h in HOLDS:
                j = i + h
                if j < n and closes[i] > 0:
                    fwd[str(h)] = round(float(closes[j] / closes[i] - 1.0), 6)
            rows.append(
                {
                    "date": str(dates[i]),
                    "close": round(float(closes[i]), 3),
                    "short": round(float(short[i]), 2),
                    "long": round(float(long_[i]), 2),
                    "trend": bool(trend[i]),
                    "bucket": b,
                    "fwd": fwd,
                }
            )
        if rows:
            result["stocks"][symbol] = {"name": watch[symbol], "signals": rows}

    del candles
    gc.collect()
    return result


def print_report(results: dict) -> None:
    for w in ("IS", "OOS-A", "OOS-B", "OOS-C"):
        if w not in results:
            continue
        r = results[w]
        print("\n" + "=" * 100)
        print("【%s】%s ~ %s" % (w, r["start"], r["end"]))
        print("=" * 100)
        for sym in sorted(r["stocks"]):
            st = r["stocks"][sym]
            print("\n  %s %s（%d 条信号）" % (sym, st["name"], len(st["signals"])))
            print("    %-12s %8s %6s %6s %-5s %-38s %s" % ("日期", "收盘", "短", "长", "趋势", "桶", "前向收益 5/10/20/40/60"))
            for row in st["signals"]:
                f = row["fwd"]
                fwd_s = "/".join("%+.1f%%" % (f[h] * 100) for h in ("5", "10", "20", "40", "60") if h in f)
                print("    %-12s %8.2f %6.1f %6.1f %-5s %-38s %s" % (
                    row["date"], row["close"], row["short"], row["long"],
                    "多头" if row["trend"] else "空头",
                    BUCKET_NAMES[row["bucket"]][:38], fwd_s,
                ))


def main() -> None:
    ap = argparse.ArgumentParser(description="pin30 信号明细")
    ap.add_argument("--windows", nargs="+", default=["IS", "A", "B", "C"])
    ap.add_argument("--out", default="data/pin30_cases.json")
    ap.add_argument("--named-only", action="store_true", help="只处理三只点名股")
    args = ap.parse_args()

    watch = dict(NAMED)
    if not args.named_only:
        watch.update(load_medical_codes())

    out_path = Path(args.out)
    results: dict = {}
    if out_path.exists():
        try:
            results = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            results = {}

    for window in args.windows:
        results[WINDOW_LABELS[window]] = run_window(window, watch)
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print_report(results)
    print("\n结构化快照已写入 %s" % out_path)


if __name__ == "__main__":
    main()
