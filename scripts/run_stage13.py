#!/usr/bin/env python3
"""阶段 13 第二步：全市场四段区间验证「区间化背离 + 双防线」修正体系。

## 背景

阶段 12b 的止损测试结论是「过度止损，81~95% 买入即被止损」。根因不是线错了，
是入场点错了：Jeremy 买在「反弹站上生命线后的横盘回踩」，旧回测买在「探底当天」，
生命线在探底价上方 +12~38%，所以买入即触发。

## 本脚本对比

- **旧口径（对照组）**：阶段 12b 的「探底当天买入」——深水单针基础事件
  （short<=30 且 非趋势多头 且 long<=55），当日收盘买入。
- **新口径**：四步入场序列——
  ① 底背离确认（区间摆动低点，收盘创新低，确认日 = 低点 + k）
  ② 价格收盘站上生命线（生命线 = (最近已确认顶背离区间最高 + 最近已确认底背离区间最低)/2）
  ③ 单针下 30 触发（短期随机 ≤30）
  ④ 买入（用当日收盘价）

## 持有（两组共用双防线止损）

- 第一道 生命线：收盘跌破 → 减仓；2-3 日内收盘重新站回 → 洗盘，买回（不计入离场）。
- 第二道 进攻 K 中点（(开+收)/2，栈逻辑）：收盘跌破 → 真正离场。
- 不设固定持有期（上限 60 日）；同时报固定 5/13/25/60 作参照。

## 指标（每组）

样本量 / 胜率 / 绝对收益 / 超额收益（减同期个股基线）/ MAE / MFE / 被止损比例 /
洗盘买回胜率。样本 <100 标注不作结论。

## 纪律

- 严禁前视：买入价用确认日收盘；pivot 确认等右侧 k 根走完；生命线只用「已确认」背离。
- 内存纪律：单进程逐股处理，不复制切片，不用 Pool 传大对象。

用法（仓库根目录）：
    .venv/bin/python scripts/run_stage13.py --windows IS A B C --out data/stage13_backtest.json
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from array import array
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.baseline import compute_baseline
from indicators.divergence import swing_highs, swing_lows
from indicators.macd import calc_macd
from indicators.stage13 import attack_midpoint, detect_attack_candles, upper_shadow_ratio
from strategies.filters import SymbolKind

from scripts.pin30_common import pin30_series
from scripts.run_oos_strategies import WINDOW_LABELS, WINDOWS, load_universe, peak_rss_mb

DIV_K = 3            # 区间化背离的左右 k 根（159828 用 k=3 复现全部点位）
SHORT_PIN = 30.0     # 单针下 30 阈值
LONG_DEEP_MAX = 55.0  # 旧口径深水：长期随机 ≤55
MIN_N = 100          # 样本量下限，低于此标注不作结论
WARMUP_BARS = 320
MAX_HOLD = 60        # 双防线持有的上限（同时是固定持有参照的最长期）
FIXED_HOLDS = [5, 13, 25, 60]
WASHOUT_WINDOW = 3   # 洗盘判定：破生命线后 3 日内站回
SHADOW_THRESHOLDS = [0.5, 0.6, 0.7]  # 长上影线阈值
SHADOW_SELLS = [0.5, 0.7, 1.0]       # 长上影线卖出仓位


def attack_midpoint_series(
    opens: np.ndarray, closes: np.ndarray, symbol: str
) -> np.ndarray:
    """逐日「当前有效进攻 K 中点」序列（栈逻辑），无进攻 K 处为 NaN。"""
    n = len(closes)
    atk = detect_attack_candles(opens.tolist(), closes.tolist(), symbol)
    atk_set = set(atk)
    mid_of = {i: attack_midpoint(float(opens[i]), float(closes[i])) for i in atk}
    series = np.full(n, np.nan, dtype=float)
    stack: list[float] = []
    for i in range(n):
        if i in atk_set:
            stack.append(mid_of[i])
        while stack and closes[i] < stack[-1]:
            stack.pop()
        if stack:
            series[i] = stack[-1]
    return series


def build_flags(df: pd.DataFrame, symbol: str) -> dict:
    """单标的：pin30 + MACD + 区间化背离 + 生命线 + 进攻 K 中点序列。"""
    s = pin30_series(df)
    closes = s["close"]
    short = s["short"]
    long_ = s["long"]
    trend = s["trend"]
    n = len(closes)

    highs = df["high"].astype(float).to_numpy()
    lows = df["low"].astype(float).to_numpy()
    opens = df["open"].astype(float).to_numpy()

    dif, _dea, hist = calc_macd(closes.tolist())
    dif = np.asarray(dif, dtype=float)
    hist = np.asarray(hist, dtype=float)

    # 区间化摆动点（k=3）
    sh = swing_highs(highs.tolist(), DIV_K)
    sl = swing_lows(lows.tolist(), DIV_K)

    # 已确认顶背离高点（前向填充，确认日 = pivot + k，无前视）
    top_high = np.full(n, np.nan, dtype=float)
    for i in sorted(sh):
        cb = i + DIV_K
        if cb < n:
            top_high[cb:] = highs[i]

    # 已确认底背离低点（前向填充；收盘创新低才算新的底 = 不破底用收盘价）
    # 同时收集「底背离事件」列表：确认日 = idx + k，生命线 = (紧邻顶高 + 底低)/2。
    bottom_low = np.full(n, np.nan, dtype=float)
    bottom_idx_series = np.full(n, -1, dtype=int)
    bottom_events: list[tuple[int, float, float]] = []  # (confirm_bar, bottom_low, top_high)
    prev_close: float | None = None
    ti = 0
    for i in sl:
        while ti < len(sh) and sh[ti] < i:
            ti += 1
        top_high_i = float(highs[sh[ti - 1]]) if ti > 0 else np.nan
        c = closes[i]
        is_new_low = prev_close is None or c < prev_close
        if is_new_low:
            cb = i + DIV_K
            if cb < n:
                bottom_low[cb:] = lows[i]
                bottom_idx_series[cb:] = i
                if not np.isnan(top_high_i):
                    bottom_events.append((cb, float(lows[i]), top_high_i))
        prev_close = c

    # 生命线序列（顶/底都确认才定义）
    lifeline = np.where(
        (~np.isnan(top_high)) & (~np.isnan(bottom_low)),
        (top_high + bottom_low) / 2.0,
        np.nan,
    )

    # 进攻 K 中点序列
    attack_series = attack_midpoint_series(opens, closes, symbol)

    return {
        "close": closes, "high": highs, "low": lows, "open": opens,
        "short": short, "long": long_, "trend": trend,
        "dif": dif, "hist": hist,
        "lifeline": lifeline,
        "attack_series": attack_series,
        "bottom_idx_series": bottom_idx_series,
        "bottom_events": bottom_events,
    }


def _rolling_sma(values: np.ndarray, period: int) -> np.ndarray:
    csum = np.concatenate(([0.0], np.cumsum(values)))
    i = np.arange(len(values))
    s = np.maximum(0, i - period + 1)
    return (csum[i + 1] - csum[s]) / (i - s + 1)


class Accum:
    """运行累加器（ret 用运行和；MAE/MFE 存数组供中位数）。"""

    def __init__(self):
        self.mae = array("d")
        self.mfe = array("d")
        self.n = 0
        self.win = 0
        self.sum_ret = 0.0
        self.stopped = 0
        self.lifeline_broken = 0
        self.immediate_break = 0
        self.washout = 0
        self.washout_win = 0

    def add(self, ret: float, mae: float, mfe: float, stopped: bool,
            lifeline_broken: bool, immediate_break: bool, washout: bool):
        self.mae.append(mae)
        self.mfe.append(mfe)
        self.n += 1
        if ret > 0:
            self.win += 1
        self.sum_ret += ret
        if stopped:
            self.stopped += 1
        if lifeline_broken:
            self.lifeline_broken += 1
        if immediate_break:
            self.immediate_break += 1
        if washout:
            self.washout += 1
            if ret > 0:
                self.washout_win += 1


def _stat(acc: Accum, base_win: float, base_ret: float) -> dict:
    n = acc.n
    m = np.frombuffer(acc.mae, dtype=np.float64) if n else np.empty(0)
    f = np.frombuffer(acc.mfe, dtype=np.float64) if n else np.empty(0)
    return {
        "n": n,
        "win_rate": round(acc.win / n, 6) if n else 0.0,
        "avg_return": round(acc.sum_ret / n, 6) if n else 0.0,
        "excess_win_rate": round(acc.win / n - base_win, 6) if n else 0.0,
        "excess_return": round(acc.sum_ret / n - base_ret, 6) if n else 0.0,
        "mae_mean": round(float(m.mean()), 6) if m.size else 0.0,
        "mae_median": round(float(np.median(m)), 6) if m.size else 0.0,
        "mfe_mean": round(float(f.mean()), 6) if f.size else 0.0,
        "mfe_median": round(float(np.median(f)), 6) if f.size else 0.0,
        "stopped_ratio": round(acc.stopped / n, 6) if n else 0.0,
        "lifeline_broken_ratio": round(acc.lifeline_broken / n, 6) if n else 0.0,
        "immediate_break_ratio": round(acc.immediate_break / n, 6) if n else 0.0,
        "washout_ratio": round(acc.washout / n, 6) if n else 0.0,
        "washout_win_rate": round(acc.washout_win / acc.washout, 6) if acc.washout else 0.0,
        "insufficient": n < MIN_N,
    }


def simulate_holding(fl: dict, entry_i: int, lifeline: float, end_i: int) -> dict:
    """双防线止损：从 entry_i 次日开始，返回 exit_i / 是否被止损 / 破生命线 / 洗盘。"""
    close = fl["close"]
    attack = fl["attack_series"]
    n = len(close)
    exit_i = min(entry_i + MAX_HOLD, end_i, n - 1)
    stopped = False
    lifeline_broken = False
    immediate_break = False
    washout = False
    break_day = -1
    for t in range(entry_i + 1, exit_i + 1):
        A = attack[t]
        if not np.isnan(A) and close[t] < A:
            exit_i = t
            stopped = True
            break
        if close[t] < lifeline:
            lifeline_broken = True
            if t - entry_i <= 5:
                immediate_break = True
            if break_day < 0:
                break_day = t
        elif break_day >= 0 and 0 < t - break_day <= WASHOUT_WINDOW:
            washout = True
    return {
        "exit_i": exit_i,
        "stopped": stopped,
        "lifeline_broken": lifeline_broken,
        "immediate_break": immediate_break,
        "washout": washout,
    }


def run_window(window: str) -> dict:
    label = WINDOW_LABELS[window]
    start, end = (date.fromisoformat(x) for x in WINDOWS[window])
    from market.calendar import trading_days

    days = trading_days(start, end)
    lookback = len(days) + WARMUP_BARS
    print("\n" + "=" * 88)
    print("【%s】%s ~ %s（%d 交易日，回看 %d 根）" % (label, start, end, len(days), lookback), flush=True)

    t0 = time.time()
    candles, _kind_map = load_universe(end, lookback, kinds=(SymbolKind.STOCK,), verbose=True)
    print("  加载个股 %d 只，%.1fs，RSS峰值 %.0fMB" % (len(candles), time.time() - t0, peak_rss_mb()), flush=True)

    symbols = sorted(candles)
    start_ord = start.toordinal()
    end_ord = end.toordinal()

    # 累加器
    new_primary = Accum()
    old_primary = Accum()
    new_fixed = {h: Accum() for h in FIXED_HOLDS}
    old_fixed = {h: Accum() for h in FIXED_HOLDS}

    t0 = time.time()
    n_done = 0
    n_new = 0
    n_old = 0
    # 长上影线卖出（步骤三）：threshold × sell 组合的 return 累加（与 base 对比）
    shadow_ret: dict[tuple[float, float], float] = {(th, s): 0.0 for th in SHADOW_THRESHOLDS for s in SHADOW_SELLS}
    shadow_n: dict[tuple[float, float], int] = {(th, s): 0 for th in SHADOW_THRESHOLDS for s in SHADOW_SELLS}
    shadow_mae: dict[tuple[float, float], float] = {(th, s): 0.0 for th in SHADOW_THRESHOLDS for s in SHADOW_SELLS}
    shadow_triggered = 0
    for symbol in symbols:
        df = candles[symbol]
        n = len(df)
        if n < 200:  # 需要足够 warmup 才算得出 MACD / pivot
            continue
        fl = build_flags(df, symbol)
        close = fl["close"]
        low = fl["low"]
        ordinals = np.array([d.toordinal() for d in df["date"].to_numpy()], dtype=np.int64)
        i0 = int(np.searchsorted(ordinals, start_ord, side="left"))
        i1 = int(np.searchsorted(ordinals, end_ord, side="right"))
        if i1 - i0 < 2:
            continue

        lifeline = fl["lifeline"]
        short = fl["short"]
        long_ = fl["long"]
        trend = fl["trend"]

        # ---- 新口径：底背离确认后，站上生命线 + 单针 → 买入 ----
        for (cb, bot_low, top_high) in fl["bottom_events"]:
            if cb < i0 or cb >= i1:
                continue
            L = (top_high + bot_low) / 2.0
            # 从确认日起，找首个「收盘站上生命线 且 单针」的交易日
            entry_i = -1
            for t in range(cb, i1):
                if close[t] > L and short[t] <= SHORT_PIN and t + 1 < n:
                    entry_i = t
                    break
            if entry_i < 0:
                continue
            entry_close = close[entry_i]
            res = simulate_holding(fl, entry_i, L, i1 - 1)
            j = res["exit_i"]
            ret = float(close[j] / entry_close - 1.0)
            mae = float(low[entry_i + 1 : j + 1].min() / entry_close - 1.0)
            mfe = float(fl["high"][entry_i + 1 : j + 1].max() / entry_close - 1.0)
            new_primary.add(ret, mae, mfe, res["stopped"], res["lifeline_broken"], res["immediate_break"], res["washout"])
            n_new += 1
            # ---- 步骤三：长上影线卖出规则（叠加在已入场样本上） ----
            o = fl["open"]
            h_ = fl["high"]
            lo = fl["low"]
            for th in SHADOW_THRESHOLDS:
                shadow_day = -1
                for t in range(entry_i + 1, j + 1):
                    if upper_shadow_ratio(float(o[t]), float(h_[t]), float(lo[t]), float(close[t])) >= th:
                        shadow_day = t
                        break
                if shadow_day >= 0:
                    r_shadow = float(close[shadow_day] / entry_close - 1.0)
                    for s in SHADOW_SELLS:
                        r_comb = s * r_shadow + (1.0 - s) * ret
                        m_comb = float(lo[entry_i + 1 : shadow_day + 1].min() / entry_close - 1.0)
                        shadow_ret[(th, s)] += r_comb
                        shadow_mae[(th, s)] += m_comb
                        shadow_n[(th, s)] += 1
                    shadow_triggered += 1
            # 固定持有参照
            for h in FIXED_HOLDS:
                if entry_i + h < n:
                    rh = float(close[entry_i + h] / entry_close - 1.0)
                    mh = float(low[entry_i + 1 : entry_i + h + 1].min() / entry_close - 1.0)
                    fh = float(fl["high"][entry_i + 1 : entry_i + h + 1].max() / entry_close - 1.0)
                    new_fixed[h].add(rh, mh, fh, False, False, False, False)

        # ---- 旧口径：探底当天买入（深水单针） ----
        for t in range(i0, i1):
            if (short[t] <= SHORT_PIN) and (not trend[t]) and (long_[t] <= LONG_DEEP_MAX) and (t + 1 < n):
                if np.isnan(lifeline[t]):
                    continue
                entry_i = t
                entry_close = close[t]
                L = float(lifeline[t])
                res = simulate_holding(fl, entry_i, L, i1 - 1)
                j = res["exit_i"]
                ret = float(close[j] / entry_close - 1.0)
                mae = float(low[entry_i + 1 : j + 1].min() / entry_close - 1.0)
                mfe = float(fl["high"][entry_i + 1 : j + 1].max() / entry_close - 1.0)
                old_primary.add(ret, mae, mfe, res["stopped"], res["lifeline_broken"], res["immediate_break"], res["washout"])
                n_old += 1
                for h in FIXED_HOLDS:
                    if entry_i + h < n:
                        rh = float(close[entry_i + h] / entry_close - 1.0)
                        mh = float(low[entry_i + 1 : entry_i + h + 1].min() / entry_close - 1.0)
                        fh = float(fl["high"][entry_i + 1 : entry_i + h + 1].max() / entry_close - 1.0)
                        old_fixed[h].add(rh, mh, fh, False, False, False, False)

        n_done += 1
        if n_done % 500 == 0:
            gc.collect()
            print("    ...%d/%d 只，新%d 旧%d，%.1fs，RSS峰值 %.0fMB" % (n_done, len(symbols), n_new, n_old, time.time() - t0, peak_rss_mb()), flush=True)

    print("  模拟完成，%d 只，新口径 %d 次，旧口径 %d 次，%.1fs" % (n_done, n_new, n_old, time.time() - t0), flush=True)

    # 基线（个股宇宙）
    base = compute_baseline(candles, symbols, "stock", start, end, FIXED_HOLDS)
    baselines = {str(h.hold_days): {"win_rate": h.win_rate, "avg_return": h.avg_return} for h in base.holds}

    result: dict = {
        "window": label, "start": str(start), "end": str(end),
        "n_new": n_new, "n_old": n_old, "baselines": baselines,
    }

    def _primary_stat(acc: Accum) -> dict:
        n = acc.n
        m = np.frombuffer(acc.mae, dtype=np.float64) if n else np.empty(0)
        f = np.frombuffer(acc.mfe, dtype=np.float64) if n else np.empty(0)
        return {
            "n": n,
            "win_rate": round(acc.win / n, 6) if n else 0.0,
            "avg_return": round(acc.sum_ret / n, 6) if n else 0.0,
            "mae_mean": round(float(m.mean()), 6) if m.size else 0.0,
            "mfe_mean": round(float(f.mean()), 6) if f.size else 0.0,
            "stopped_ratio": round(acc.stopped / n, 6) if n else 0.0,
            "lifeline_broken_ratio": round(acc.lifeline_broken / n, 6) if n else 0.0,
            "immediate_break_ratio": round(acc.immediate_break / n, 6) if n else 0.0,
            "washout_ratio": round(acc.washout / n, 6) if n else 0.0,
            "washout_win_rate": round(acc.washout_win / acc.washout, 6) if acc.washout else 0.0,
            "insufficient": n < MIN_N,
        }

    result["new"] = {"primary": _primary_stat(new_primary), "fixed": {}}
    result["old"] = {"primary": _primary_stat(old_primary), "fixed": {}}
    # 步骤三：长上影线卖出（新口径样本；每格 = 平均收益% / MAE% / n）
    result["shadow"] = {}
    for th in SHADOW_THRESHOLDS:
        result["shadow"][str(th)] = {}
        for s in SHADOW_SELLS:
            k = (th, s)
            nn = shadow_n[k]
            result["shadow"][str(th)][str(s)] = {
                "avg_return": round(shadow_ret[k] / nn, 6) if nn else 0.0,
                "mae_mean": round(shadow_mae[k] / nn, 6) if nn else 0.0,
                "n": nn,
            }
    result["shadow_triggered"] = shadow_triggered
    result["base_new"] = {
        "avg_return": round(new_primary.sum_ret / new_primary.n, 6) if new_primary.n else 0.0,
        "mae_mean": round(float(np.frombuffer(new_primary.mae, dtype=np.float64).mean()), 6) if new_primary.n else 0.0,
    }
    for h in FIXED_HOLDS:
        bw = baselines[str(h)]["win_rate"]
        br = baselines[str(h)]["avg_return"]
        result["new"]["fixed"][str(h)] = _stat(new_fixed[h], bw, br)
        result["old"]["fixed"][str(h)] = _stat(old_fixed[h], bw, br)

    del candles
    gc.collect()
    return result


def print_report(results: dict) -> None:
    labels = [l for l in ("IS", "OOS-A", "OOS-B", "OOS-C") if l in results]
    print("\n" + "=" * 130)
    print("双防线持有（不设固定期，上限 60 日）：胜率% / 绝对收益% / MAE% / MFE% / 被止损% / 破生命线% / 5日内破线% / 洗盘% / 洗盘买回胜率%")
    print("=" * 130)
    hdr = "    %-10s" % "口径"
    for l in labels:
        hdr += "%24s" % l
    print(hdr)
    for grp, name in (("new", "新口径"), ("old", "旧口径")):
        row = "    %-10s" % name
        for l in labels:
            c = results[l][grp]["primary"]
            row += "%24s" % ("%s%.0f/%+.2f/%.1f/%.1f/%.0f/%.0f/%.0f/%.0f/%.0f" % (
                "*" if c["insufficient"] else "", c["win_rate"] * 100, c["avg_return"] * 100,
                c["mae_mean"] * 100, c["mfe_mean"] * 100, c["stopped_ratio"] * 100,
                c["lifeline_broken_ratio"] * 100, c["immediate_break_ratio"] * 100,
                c["washout_ratio"] * 100, c["washout_win_rate"] * 100))
        print(row)

    print("\n" + "=" * 120)
    print("固定持有参照（5/13/25/60）：胜率% / 绝对收益% | 超额胜率pp / 超额收益%  (n)")
    print("=" * 120)
    for h in FIXED_HOLDS:
        print("\n  持有 %d 日：" % h)
        hdr = "      %-10s" % "口径"
        for l in labels:
            hdr += "%24s" % l
        print(hdr)
        for grp, name in (("new", "新口径"), ("old", "旧口径")):
            row = "      %-10s" % name
            for l in labels:
                c = results[l][grp]["fixed"][str(h)]
                row += "%24s" % ("%s%.0f/%+.2f|%+.1f/%+.2f(%d)" % (
                    "*" if c["insufficient"] else "", c["win_rate"] * 100, c["avg_return"] * 100,
                    c["excess_win_rate"] * 100, c["excess_return"] * 100, c["n"]))
            print(row)
    bl = "      %-10s" % "基线"
    for l in labels:
        b = results[l]["baselines"][str(FIXED_HOLDS[0])]
        bl += "%24s" % ("%.1f / %+.2f" % (b["win_rate"] * 100, b["avg_return"] * 100))
    print(bl + "  (5日基线)")

    print("\n" + "=" * 120)
    print("步骤三：长上影线卖出（新口径已入场样本）—— 平均收益% / MAE% (n)；触发比例")
    print("=" * 120)
    for l in labels:
        d = results[l]
        base = d["base_new"]
        n_new = d["new"]["primary"]["n"]
        print("\n  【%s】 base 收益 %+.2f%% / MAE %.1f%% (n=%d)，长上影线触发 %d 次" % (
            l, base["avg_return"] * 100, base["mae_mean"] * 100, n_new, d["shadow_triggered"]))
        hdr = "      %-16s" % "卖出仓位"
        for th in SHADOW_THRESHOLDS:
            hdr += "%18s" % ("阈值%d%%" % (th * 100))
        print(hdr)
        for s in SHADOW_SELLS:
            row = "      %-16s" % ("卖%d%%" % (s * 100))
            for th in SHADOW_THRESHOLDS:
                c = d["shadow"][str(th)][str(s)]
                row += "%18s" % ("%+.2f/%.1f(%d)" % (c["avg_return"] * 100, c["mae_mean"] * 100, c["n"]))
            print(row)


def main() -> None:
    ap = argparse.ArgumentParser(description="阶段13 区间化背离+双防线 四段验证")
    ap.add_argument("--windows", nargs="+", default=["IS", "A", "B", "C"])
    ap.add_argument("--out", default="data/stage13_backtest.json")
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
