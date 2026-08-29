#!/usr/bin/env python3
"""阶段 12b：pin30 单针下30 分桶——波段持有期 5/13/25/60 + MFE/MAE（补充测算）。

## 背景

阶段 12（run_pin30_bucket.py）用持有期 5/10/20/40/60 测了四桶，结论：
桶1（原始 pin30）20 日四段全负；桶3（深水单针）40/60 日四段全正但弱。

Jeremy 两点要求：
1. 持有期改成 **5 / 13 / 25 / 60**（对齐主图均线 MA5/MA13/MA25/MA60），
   原来的 10/20/40 是等比数，跟框架没对应关系。
2. 每个持有期窗口内加波段过程指标：
   - MFE（最大浮盈）= 窗口内最高价 / 信号收盘价 - 1
   - MAE（最大浮亏）= 窗口内最低价 / 信号收盘价 - 1
   - MFE/|MAE|（盈亏结构）

## 口径（与阶段 12 完全一致，复用 pin30_common）

基础事件 = 短期随机 <= 30（short=(C-LLV(L,3))/(HHV(C,3)-LLV(L,3)+eps)*100）。
四桶 = bucket_of(trend, long)。趋势多头 = ST_RAW>LT_RAW 且 C>LT_RAW。
收益全部减同期同宇宙（个股）基线 compute_baseline；绝对/超额分列。

窗口：i 为信号日（收盘 close[i] 为信号价），持有 h 日后：
- 绝对收益 = close[i+h]/close[i]-1
- MFE = max(high[i+1..i+h]) / close[i] - 1
- MAE = min(low[i+1..i+h])  / close[i] - 1
- MFE/|MAE| = mfe_mean / |mae_mean|（比率用均值比，另附逐信号比率均值）

内存纪律沿用：单标的向量化 + pandas rolling，不复制切片，不 Pool 传大对象。

用法（仓库根目录）：
    .venv/bin/python scripts/run_pin30_band_holds.py --windows IS A B C \
        --out data/pin30_band_holds.json
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
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.baseline import compute_baseline
from strategies.filters import SymbolKind
from strategies.pin30.config import default_config as pin30_default_config

from scripts.pin30_common import BUCKET_NAMES, pin30_series
from scripts.run_oos_strategies import WINDOW_LABELS, WINDOWS, load_universe, peak_rss_mb

HOLDS = [5, 13, 25, 60]
SHORT_THRESHOLD = 30.0
MIN_N = 100  # 样本量红线：低于此值标注「样本不足，不作结论」
WARMUP_BARS = 320  # 覆盖 MA114 + EMA(10,10) + 长随机(20) + 缓冲

BUCKETS = [1, 2, 3, 4]


def _stats(rets, mfes, maes, base_win, base_ret, signals) -> dict:
    arr = np.asarray(rets, dtype=float) if len(rets) else np.empty(0)
    mf = np.asarray(mfes, dtype=float) if len(mfes) else np.empty(0)
    ma = np.asarray(maes, dtype=float) if len(maes) else np.empty(0)
    n = int(arr.size)
    win = float((arr > 0).mean()) if n else 0.0
    avg = float(arr.mean()) if n else 0.0
    mfe_mean = float(mf.mean()) if mf.size else 0.0
    mae_mean = float(ma.mean()) if ma.size else 0.0
    mfe_median = float(np.median(mf)) if mf.size else 0.0
    mae_median = float(np.median(ma)) if ma.size else 0.0
    ratio = (mfe_mean / abs(mae_mean)) if mae_mean != 0.0 else float("nan")
    # 逐信号 MFE/|MAE| 的均值（|MAE|<1e-6 的视为缺失，避免除零放大）
    per_signal = np.nan
    if mf.size and ma.size:
        abs_ma = np.abs(ma)
        ok = abs_ma > 1e-6
        if ok.any():
            per_signal = float((mf[ok] / abs_ma[ok]).mean())
    return {
        "signals": signals,
        "n": n,
        "win_rate": round(win, 6),
        "avg_return": round(avg, 6),
        "excess_win_rate": round(win - base_win, 6),
        "excess_return": round(avg - base_ret, 6),
        "mfe_mean": round(mfe_mean, 6),
        "mae_mean": round(mae_mean, 6),
        "mfe_median": round(mfe_median, 6),
        "mae_median": round(mae_median, 6),
        "mfe_over_abs_mae": round(ratio, 6) if np.isfinite(ratio) else None,
        "mfe_over_abs_mae_per_signal": round(per_signal, 6) if np.isfinite(per_signal) else None,
        "insufficient": n < MIN_N,
    }


def _fwd_arrays(closes, highs, lows, h):
    """返回 (fwd_close, mfe, mae) 三个长度 n 的数组，越界处为 NaN。

    fwd[i] = close[i+h]/close[i]-1
    mfe[i] = max(high[i+1..i+h])/close[i]-1
    mae[i] = min(low[i+1..i+h])/close[i]-1
    """
    close_s = pd.Series(closes)
    fwd = (close_s.shift(-h) / close_s - 1.0).to_numpy(dtype=float)
    high_s = pd.Series(highs)
    low_s = pd.Series(lows)
    mfe = (high_s.rolling(h, min_periods=h).max().shift(-h) / close_s - 1.0).to_numpy(dtype=float)
    mae = (low_s.rolling(h, min_periods=h).min().shift(-h) / close_s - 1.0).to_numpy(dtype=float)
    return fwd, mfe, mae


def run_window(window: str) -> dict:
    label = WINDOW_LABELS[window]
    start, end = (date.fromisoformat(x) for x in WINDOWS[window])
    from market.calendar import trading_days

    days = trading_days(start, end)
    lookback = len(days) + WARMUP_BARS
    print("\n" + "=" * 80)
    print("【%s】%s ~ %s（%d 交易日，回看 %d 根）" % (label, start, end, len(days), lookback), flush=True)

    t0 = time.time()
    candles, _kind_map = load_universe(end, lookback, kinds=(SymbolKind.STOCK,), verbose=True)
    print("  加载个股 %d 只，%.1fs，RSS峰值 %.0fMB" % (len(candles), time.time() - t0, peak_rss_mb()), flush=True)

    symbols = sorted(candles)
    start_ord = start.toordinal()
    end_ord = end.toordinal()
    cfg = pin30_default_config()
    min_bars = cfg.min_bars

    # 分桶累计：rets[b][h] / mfes[b][h] / maes[b][h] = list
    rets: dict[int, dict[int, list]] = {b: {h: [] for h in HOLDS} for b in BUCKETS}
    mfes: dict[int, dict[int, list]] = {b: {h: [] for h in HOLDS} for b in BUCKETS}
    maes: dict[int, dict[int, list]] = {b: {h: [] for h in HOLDS} for b in BUCKETS}
    sig: dict[int, int] = {b: 0 for b in BUCKETS}

    t0 = time.time()
    for si, symbol in enumerate(symbols, 1):
        df = candles[symbol]
        n = len(df)
        if n < min_bars:
            continue
        s = pin30_series(df)
        closes = s["close"]
        short = s["short"]
        long_ = s["long"]
        trend = s["trend"]
        highs = df["high"].astype(float).to_numpy()
        lows = df["low"].astype(float).to_numpy()
        ordinals = np.array([d.toordinal() for d in df["date"].to_numpy()], dtype=np.int64)

        i0 = int(np.searchsorted(ordinals, start_ord, side="left"))
        i1 = int(np.searchsorted(ordinals, end_ord, side="right"))

        idx = np.arange(i0, i1)
        if idx.size == 0:
            continue
        mask = (short[idx] <= SHORT_THRESHOLD) & (idx >= min_bars - 1)
        ev = idx[mask]
        if ev.size == 0:
            continue

        ev_trend = trend[ev]
        ev_long = long_[ev]
        b_arr = np.zeros(ev.size, dtype=int)
        b_arr[(ev_trend) & (ev_long >= 80.0)] = 1
        b_arr[(ev_trend) & (ev_long >= 50.0) & (ev_long < 80.0)] = 2
        b_arr[(~ev_trend) & (ev_long <= 55.0)] = 3
        b_arr[b_arr == 0] = 4

        for b in BUCKETS:
            bi = ev[b_arr == b]
            if bi.size == 0:
                continue
            sig[b] += int(bi.size)
            base = closes[bi]
            for h in HOLDS:
                fwd, mfe, mae = _fwd_arrays(closes, highs, lows, h)
                f = fwd[bi]
                mf = mfe[bi]
                ma = mae[bi]
                ok = ~np.isnan(f) & ~np.isnan(mf) & ~np.isnan(ma)
                if not ok.any():
                    continue
                rets[b][h].extend(f[ok].tolist())
                mfes[b][h].extend(mf[ok].tolist())
                maes[b][h].extend(ma[ok].tolist())

        if si % 2000 == 0:
            gc.collect()
            print("    ...%d/%d 只，%.1fs，RSS峰值 %.0fMB" % (si, len(symbols), time.time() - t0, peak_rss_mb()), flush=True)

    print("  扫描完成，%.1fs，RSS峰值 %.0fMB" % (time.time() - t0, peak_rss_mb()), flush=True)

    # 基线（个股宇宙，同持有期）
    base = compute_baseline(candles, symbols, "stock", start, end, HOLDS)
    baselines = {
        str(h.hold_days): {"win_rate": h.win_rate, "avg_return": h.avg_return, "n": h.n}
        for h in base.holds
    }

    result: dict = {"window": label, "start": str(start), "end": str(end), "universe_size": len(symbols)}
    result["baselines"] = baselines
    result["buckets"] = {}
    for b in BUCKETS:
        entry = {"name": BUCKET_NAMES[b], "signals": sig[b], "holds": {}}
        for h in HOLDS:
            entry["holds"][str(h)] = _stats(
                rets[b][h], mfes[b][h], maes[b][h],
                baselines[str(h)]["win_rate"], baselines[str(h)]["avg_return"], sig[b],
            )
        result["buckets"][str(b)] = entry

    del candles, rets, mfes, maes
    gc.collect()
    return result


def print_report(results: dict) -> None:
    labels = [l for l in ("IS", "OOS-A", "OOS-B", "OOS-C") if l in results]
    names = {str(b): results[labels[0]]["buckets"][str(b)]["name"] for b in BUCKETS}
    print("\n" + "=" * 140)
    print("pin30 单针下30 分桶 × 波段持有期 5/13/25/60（超额 pp / 超额%% / 绝对%% | MFE%% / MAE%% / MFE÷|MAE|）")
    print("（* = 样本量 < %d，不作结论）" % MIN_N)
    print("=" * 140)
    for h in HOLDS:
        print("\n  —— 持有 %d 日 ——" % h)
        hdr = "    %-40s" % "桶"
        for l in labels:
            hdr += "%24s" % l
        print(hdr)
        for b in BUCKETS:
            row = "    %-40s" % names[str(b)]
            for l in labels:
                c = results[l]["buckets"][str(b)]["holds"][str(h)]
                mark = "*" if c["insufficient"] else " "
                ratio = c["mfe_over_abs_mae"]
                ratio_s = "%.2f" % ratio if ratio is not None else "—"
                row += "%24s" % (
                    "%s%+.1f/%+.2f/%+.2f|%+.1f/%+.1f/%s"
                    % (
                        mark,
                        c["excess_win_rate"] * 100,
                        c["excess_return"] * 100,
                        c["avg_return"] * 100,
                        c["mfe_mean"] * 100,
                        c["mae_mean"] * 100,
                        ratio_s,
                    )
                )
            print(row)
        bl = "    %-40s" % "[基线 胜率%/均值%]"
        for l in labels:
            b = results[l]["baselines"][str(h)]
            bl += "%24s" % ("%.1f / %+.2f" % (b["win_rate"] * 100, b["avg_return"] * 100))
        print(bl)
    # 样本量单独一表（供判断是否够）
    print("\n  —— 样本量 n（有效前向收益条数）——")
    hdr = "    %-40s" % "桶"
    for l in labels:
        hdr += "%12s" % l
    print(hdr)
    for b in BUCKETS:
        row = "    %-40s" % names[str(b)]
        for l in labels:
            c = results[l]["buckets"][str(b)]["holds"][str(5)]
            row += "%12s" % ("%s%d" % ("*" if c["insufficient"] else " ", c["n"]))
        print(row)


def main() -> None:
    ap = argparse.ArgumentParser(description="pin30 单针下30 分桶——波段持有期 5/13/25/60")
    ap.add_argument("--windows", nargs="+", default=["IS", "A", "B", "C"])
    ap.add_argument("--out", default="data/pin30_band_holds.json")
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
