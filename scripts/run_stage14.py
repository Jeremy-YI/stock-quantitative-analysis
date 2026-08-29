#!/usr/bin/env python3
"""阶段 14 第二步~第四步：全市场四段验证「MACD 柱状阶段顶底进出场 + 三条线洗盘判别器」。

## 背景

阶段 13 把三条线当「站上生命线才能买」的入场过滤器，结果是「修好机制不赚钱」。
Jeremy 澄清：大跌买 = MACD 柱状阶段性底部；高点卖 = MACD 柱状阶段性顶部；三条线
（阴量定价线 / 生命线 / 进攻K）是用来辅助「单针下30/20 是否是主力洗盘」的判别器，
**不参与入场判定**。

## 新架构

- **入场**：MACD 柱状阶段性底部（绿柱最深后开始收缩）+ 单针下30 触发 → 买（大跌当天，
  不等站上任何线）。确认日 = 收缩第一天，尾盘买用收盘价。
- **出场**：MACD 柱状阶段性顶部（红柱最高后开始收缩）→ 卖出当前仓位 50%。
- **三条线**：单针触发时判定洗盘 vs 破位——
  - 回踩不破（任一/全部线未破）→ 主力洗盘 → 买/加仓；
  - 已破且连续 2 日收盘不收回 → 真破位 → 不买/离场。
- **破位容错**：连续 2 个交易日收盘跌破才算破，单日破不算（对照「单日破即算破」）。

## 三组对照（第二步）

1. 纯单针（阶段12/13 旧口径：short<=30 且 非趋势 且 long<=55，探底当天买，固定 25/60 持有）
2. 单针 + MACD 柱状阶段底部（入场加确认：阶段底确认日 + 近 P 日有单针，固定 25/60 持有）
3. 完整架构（阶段底部入场 + 阶段顶部卖 50% + 三条线洗盘判别加仓 + 2 日容错，仓位级记账）

## 指标

样本量 / 胜率 / 绝对收益 / 超额收益（减同期个股基线）/ MAE / MFE / 平均持有天数 / 换手次数。

## 第三步（最核心）：三条线作为洗盘判别器的价值检验

不是看预测力，而是看能否分开两组：单针触发时
- 组A「判为洗盘」（回踩不破线）
- 组B「判为破位」（已破且连续 2 日不收回）
比两组后续 5/13/25/60 日收益差。线分别测：生命线单用 / 阴量线单用 / 进攻K单用 /
任一不破 / 全部不破。若两组收益无显著差异 → 该线无信息量，照实说。

## 第四步：完整仓位循环回测（3-2-2-1）

- 建仓 3-2-2-1（合计 8 成，留 2 成预备队）：首笔 3 成（阶段底+单针入场），加仓 2/2/1 成
  （持仓期间单针 + 回踩不破 = 洗盘判别加仓）。
- 阶段性顶部卖当前仓位 50%。
- 仓位级现金流记账（阶段 13 遗留项）。对照：买入持有满仓 / 固定 50%。

## 纪律

- 严禁前视：买入价用确认日收盘；柱状极值只用已收盘 bar；三条线只用已确认摆动点。
- 所有收益减基线，绝对/超额分列；样本 <100 标注不作结论。
- 不许编数字；完整架构若不如纯单针，照实说。
- 内存纪律：单进程逐股处理，不复制切片，不用 Pool 传大对象。

用法（仓库根目录）：
    .venv/bin/python scripts/run_stage14.py --windows IS A B C --out data/stage14_backtest.json
    .venv/bin/python scripts/run_stage14.py --windows IS --limit 300   # 烟囱测试
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
from indicators.macd import calc_macd
from indicators.stage14 import (
    attack_defense_series,
    detect_hist_stage_bottoms,
    detect_hist_stage_tops,
    lifeline_series,
    line_broken_2day,
    line_broken_1day,
    yin_volume_line_series,
)
from strategies.filters import SymbolKind

from scripts.pin30_common import pin30_series
from scripts.run_oos_strategies import WINDOW_LABELS, WINDOWS, load_universe, peak_rss_mb

DIV_K = 3                # 区间化摆动点 k（与 stage13 一致，复现生命线锚点）
SHORT_PIN = 30.0         # 单针下30 主口径
LONG_DEEP_MAX = 55.0     # 旧口径深水：长期随机 ≤55
PIN_WINDOW = 5           # 阶段底确认日往前找单针的窗口（交易日）
STAGE_NS = (5, 10, 20)   # 柱状极值回看档
STAGE_N_PRIMARY = 5      # 主口径
FIXED_HOLDS = [25, 60]   # 固定持有参照（组1/组2）
DISCRIM_HOLDS = [5, 13, 25, 60]  # 判别器前向收益
MIN_N = 100              # 样本量下限
WARMUP_BARS = 320
TRANCHES = [0.3, 0.2, 0.2, 0.1]  # 3-2-2-1
RESERVE = 0.2            # 留 2 成预备队

LINES = ["lifeline", "yin", "attack"]
LINE_NAMES = {
    "lifeline": "生命线",
    "yin": "阴量定价线",
    "attack": "进攻K防线",
}


def build_flags(df: pd.DataFrame, symbol: str) -> dict:
    """单标的：pin30 + MACD 柱 + 阶段顶底(N=5/10/20) + 三条线序列。"""
    s = pin30_series(df)
    closes = s["close"]
    short = s["short"]
    long_ = s["long"]
    trend = s["trend"]
    n = len(closes)

    highs = df["high"].astype(float).to_numpy()
    lows = df["low"].astype(float).to_numpy()
    opens = df["open"].astype(float).to_numpy()
    vols = df["volume"].astype(float).to_numpy()

    _, _, hist = calc_macd(closes.tolist())
    hist = np.asarray(hist, dtype=float)

    stage_bottoms = {N: set(detect_hist_stage_bottoms(hist.tolist(), N)) for N in STAGE_NS}
    stage_tops = {N: set(detect_hist_stage_tops(hist.tolist(), N)) for N in STAGE_NS}

    lifeline = np.asarray(
        lifeline_series(highs.tolist(), lows.tolist(), closes.tolist(), k=DIV_K), dtype=float
    )
    yin = np.asarray(
        yin_volume_line_series(
            highs.tolist(), lows.tolist(), opens.tolist(), closes.tolist(), vols.tolist(), k=DIV_K
        ),
        dtype=float,
    )
    attack = np.asarray(
        attack_defense_series(opens.tolist(), highs.tolist(), lows.tolist(), closes.tolist(), symbol),
        dtype=float,
    )

    return {
        "close": closes, "high": highs, "low": lows, "open": opens,
        "short": short, "long": long_, "trend": trend, "hist": hist,
        "stage_bottoms": stage_bottoms, "stage_tops": stage_tops,
        "lifeline": lifeline, "yin": yin, "attack": attack,
    }


def has_recent_pin(short: np.ndarray, t: int, window: int, thr: float) -> bool:
    lo = max(0, t - window + 1)
    return bool(np.any(short[lo : t + 1] <= thr))


def _line_break(fl: dict, line: str, t: int, broken_fn) -> bool | None:
    """某条线在 t 日的破位判定；线未定义返回 None。"""
    L = fl[line][t]
    if np.isnan(L):
        return None
    return broken_fn(fl["close"], L, t)


def _washout_any(fl: dict, t: int, broken_fn) -> bool:
    """任一不破 = 洗盘（至少一条已定义线未破）。"""
    states = [_line_break(fl, ln, t, broken_fn) for ln in LINES]
    defined = [b for b in states if b is not None]
    if not defined:
        return False  # 无线可判 → 不算洗盘
    return any(not b for b in defined)


def _washout_all(fl: dict, t: int, broken_fn) -> bool:
    """全部不破 = 洗盘（所有已定义线都未破）。"""
    states = [_line_break(fl, ln, t, broken_fn) for ln in LINES]
    defined = [b for b in states if b is not None]
    if not defined:
        return False
    return all(not b for b in defined)


class FixedAccum:
    """固定持有（组1/组2）累加器：ret/mae/mfe 存数组，胜率/均值运行累加。"""

    def __init__(self):
        self.mae = array("d")
        self.mfe = array("d")
        self.n = 0
        self.win = 0
        self.sum_ret = 0.0

    def add(self, ret: float, mae: float, mfe: float):
        self.mae.append(mae)
        self.mfe.append(mfe)
        self.n += 1
        if ret > 0:
            self.win += 1
        self.sum_ret += ret


class PositionAccum:
    """仓位循环（组3/第四步）累加器。"""

    def __init__(self):
        self.mae = array("d")
        self.mfe = array("d")
        self.ret = array("d")
        self.n = 0
        self.win = 0
        self.sum_ret = 0.0
        self.sum_holding = 0
        self.sum_turnover = 0
        # 对照：买入持有满仓 / 固定 50%（匹配同一入场）
        self.bh_full_sum = 0.0
        self.bh_half_sum = 0.0

    def add(self, ret: float, mae: float, mfe: float, holding: int, turnover: int,
            bh_full: float, bh_half: float):
        self.mae.append(mae)
        self.mfe.append(mfe)
        self.ret.append(ret)
        self.n += 1
        if ret > 0:
            self.win += 1
        self.sum_ret += ret
        self.sum_holding += holding
        self.sum_turnover += turnover
        self.bh_full_sum += bh_full
        self.bh_half_sum += bh_half


def _fixed_stat(acc: FixedAccum, base_win: float, base_ret: float) -> dict:
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
        "insufficient": n < MIN_N,
    }


def _position_stat(acc: PositionAccum) -> dict:
    n = acc.n
    m = np.frombuffer(acc.mae, dtype=np.float64) if n else np.empty(0)
    f = np.frombuffer(acc.mfe, dtype=np.float64) if n else np.empty(0)
    return {
        "n": n,
        "win_rate": round(acc.win / n, 6) if n else 0.0,
        "avg_return": round(acc.sum_ret / n, 6) if n else 0.0,
        "mae_mean": round(float(m.mean()), 6) if m.size else 0.0,
        "mfe_mean": round(float(f.mean()), 6) if f.size else 0.0,
        "avg_holding_days": round(acc.sum_holding / n, 2) if n else 0.0,
        "avg_turnover": round(acc.sum_turnover / n, 3) if n else 0.0,
        "buy_hold_full": round(acc.bh_full_sum / n, 6) if n else 0.0,
        "buy_hold_half": round(acc.bh_half_sum / n, 6) if n else 0.0,
        "insufficient": n < MIN_N,
    }


def simulate_position(fl: dict, i0: int, i1: int, N: int, pin_thr: float,
                      broken_fn, washout_mode: str) -> dict | None:
    """单股单生命周期仓位循环：3-2-2-1 建仓 + 阶段顶卖 50% + 洗盘判别加仓。

    washout_mode: "any" = 任一不破加仓；"all" = 全部不破加仓。
    """
    close = fl["close"]
    short = fl["short"]
    sb = fl["stage_bottoms"][N]
    st = fl["stage_tops"][N]

    entry = -1
    for t in range(i0, i1):
        if t in sb and has_recent_pin(short, t, PIN_WINDOW, pin_thr):
            entry = t
            break
    if entry < 0:
        return None

    washout_fn = _washout_any if washout_mode == "any" else _washout_all

    cash = 1.0 - RESERVE  # 可部署 0.8
    reserve = RESERVE
    shares = 0.0
    ti = 0
    # 首笔 3 成
    p = close[entry]
    shares = TRANCHES[0] / p
    cash -= TRANCHES[0]
    ti = 1
    turnover = 1

    eq_min = cash + reserve + shares * close[entry]
    eq_max = eq_min
    last_close = p

    for t in range(entry + 1, i1):
        # 加仓：单针 + 回踩不破，且还有档位
        if ti < 4 and short[t] <= pin_thr and washout_fn(fl, t, broken_fn):
            amt = TRANCHES[ti]
            shares += amt / close[t]
            cash -= amt
            ti += 1
            turnover += 1
        # 阶段顶：卖当前仓位 50%
        if shares > 0 and t in st:
            sell_shares = shares * 0.5
            cash += sell_shares * close[t]
            shares -= sell_shares
            turnover += 1
        eq = cash + reserve + shares * close[t]
        if eq < eq_min:
            eq_min = eq
        if eq > eq_max:
            eq_max = eq
        last_close = close[t]

    final = cash + reserve + shares * close[i1 - 1]
    ret = final - 1.0
    entry_close = close[entry]
    end_close = close[i1 - 1]
    bh_full = end_close / entry_close - 1.0
    bh_half = 0.5 * bh_full
    return {
        "ret": ret,
        "mae": eq_min - 1.0,
        "mfe": eq_max - 1.0,
        "holding": (i1 - 1) - entry,
        "turnover": turnover,
        "bh_full": bh_full,
        "bh_half": bh_half,
    }


def run_window(window: str, limit: int | None = None) -> dict:
    label = WINDOW_LABELS[window]
    start, end = (date.fromisoformat(x) for x in WINDOWS[window])
    from market.calendar import trading_days

    days = trading_days(start, end)
    lookback = len(days) + WARMUP_BARS
    print("\n" + "=" * 90)
    print("【%s】%s ~ %s（%d 交易日，回看 %d 根）" % (label, start, end, len(days), lookback), flush=True)

    t0 = time.time()
    candles, _kind_map = load_universe(end, lookback, kinds=(SymbolKind.STOCK,), verbose=True)
    print("  加载个股 %d 只，%.1fs，RSS峰值 %.0fMB" % (len(candles), time.time() - t0, peak_rss_mb()), flush=True)

    symbols = sorted(candles)
    if limit:
        symbols = symbols[:limit]
    start_ord = start.toordinal()
    end_ord = end.toordinal()

    # 第二步：组1/组2 固定持有累加器
    g1 = {h: FixedAccum() for h in FIXED_HOLDS}
    g2 = {h: FixedAccum() for h in FIXED_HOLDS}
    # 组3/第四步：仓位循环
    g3 = PositionAccum()

    # 第三步：判别器累加（per line × per hold × washout/breakdown）
    disc_keys = LINES + ["any", "all"]
    disc_2day = {
        ln: {h: {"wash": [0, 0.0, 0], "break": [0, 0.0, 0]} for h in DISCRIM_HOLDS}
        for ln in disc_keys
    }  # [n, sum_ret, win]
    disc_1day = {
        ln: {h: {"wash": [0, 0.0, 0], "break": [0, 0.0, 0]} for h in DISCRIM_HOLDS}
        for ln in disc_keys
    }

    t0 = time.time()
    n_done = 0
    n_pins = 0
    for symbol in symbols:
        df = candles[symbol]
        n = len(df)
        if n < 200:
            continue
        fl = build_flags(df, symbol)
        close = fl["close"]
        low = fl["low"]
        high = fl["high"]
        short = fl["short"]
        long_ = fl["long"]
        trend = fl["trend"]
        ordinals = np.array([d.toordinal() for d in df["date"].to_numpy()], dtype=np.int64)
        i0 = int(np.searchsorted(ordinals, start_ord, side="left"))
        i1 = int(np.searchsorted(ordinals, end_ord, side="right"))
        if i1 - i0 < 2:
            continue

        sb = fl["stage_bottoms"][STAGE_N_PRIMARY]

        # ---- 组1：纯单针（深水）----
        for t in range(i0, i1):
            if short[t] <= SHORT_PIN and (not trend[t]) and long_[t] <= LONG_DEEP_MAX and t + 1 < n:
                ec = close[t]
                for h in FIXED_HOLDS:
                    if t + h < n:
                        r = float(close[t + h] / ec - 1.0)
                        m = float(low[t + 1 : t + h + 1].min() / ec - 1.0)
                        fwd = float(high[t + 1 : t + h + 1].max() / ec - 1.0)
                        g1[h].add(r, m, fwd)

        # ---- 组2：单针 + 阶段底（入场加确认）----
        for t in range(i0, i1):
            if t in sb and has_recent_pin(short, t, PIN_WINDOW, SHORT_PIN) and t + 1 < n:
                ec = close[t]
                for h in FIXED_HOLDS:
                    if t + h < n:
                        r = float(close[t + h] / ec - 1.0)
                        m = float(low[t + 1 : t + h + 1].min() / ec - 1.0)
                        fwd = float(high[t + 1 : t + h + 1].max() / ec - 1.0)
                        g2[h].add(r, m, fwd)

        # ---- 组3/第四步：仓位循环（任一不破加仓，2 日容错）----
        res = simulate_position(fl, i0, i1, STAGE_N_PRIMARY, SHORT_PIN, line_broken_2day, "any")
        if res is not None:
            g3.add(res["ret"], res["mae"], res["mfe"], res["holding"], res["turnover"],
                   res["bh_full"], res["bh_half"])

        # ---- 第三步：判别器（单针事件按三条线分洗盘/破位，比前向收益）----
        for t in range(i0, i1):
            if short[t] <= SHORT_PIN and t + 1 < n:
                n_pins += 1
                fwd = {}
                for h in DISCRIM_HOLDS:
                    if t + h < n:
                        fwd[h] = float(close[t + h] / close[t] - 1.0)
                if not fwd:
                    continue
                for broken_fn, disc in ((line_broken_2day, disc_2day), (line_broken_1day, disc_1day)):
                    # 单线
                    for ln in LINES:
                        b = _line_break(fl, ln, t, broken_fn)
                        if b is None:
                            continue
                        key_grp = "break" if b else "wash"
                        for h, r in fwd.items():
                            cell = disc[ln][h][key_grp]
                            cell[0] += 1
                            cell[1] += r
                            if r > 0:
                                cell[2] += 1
                    # 任一不破 / 全部不破
                    states = [_line_break(fl, ln, t, broken_fn) for ln in LINES]
                    defined = [b for b in states if b is not None]
                    if defined:
                        any_wash = any(not b for b in defined)
                        all_wash = all(not b for b in defined)
                        for key, cond in (("any", any_wash), ("all", all_wash)):
                            key_grp = "wash" if cond else "break"
                            for h, r in fwd.items():
                                cell = disc[key][h][key_grp]
                                cell[0] += 1
                                cell[1] += r
                                if r > 0:
                                    cell[2] += 1

        n_done += 1
        if n_done % 1000 == 0:
            gc.collect()
            print("    ...%d/%d 只，单针 %d，%.1fs，RSS峰值 %.0fMB" % (
                n_done, len(symbols), n_pins, time.time() - t0, peak_rss_mb()), flush=True)

    print("  模拟完成，%d 只，单针 %d，%.1fs" % (n_done, n_pins, time.time() - t0), flush=True)

    # 基线（个股宇宙，固定持有期）
    base = compute_baseline(candles, symbols, "stock", start, end, FIXED_HOLDS)
    baselines = {str(h.hold_days): {"win_rate": h.win_rate, "avg_return": h.avg_return} for h in base.holds}

    result: dict = {"window": label, "start": str(start), "end": str(end), "n_pins": n_pins}
    result["baselines"] = baselines
    result["g1"] = {str(h): _fixed_stat(g1[h], baselines[str(h)]["win_rate"], baselines[str(h)]["avg_return"]) for h in FIXED_HOLDS}
    result["g2"] = {str(h): _fixed_stat(g2[h], baselines[str(h)]["win_rate"], baselines[str(h)]["avg_return"]) for h in FIXED_HOLDS}
    result["g3"] = _position_stat(g3)

    # 判别器结果整理
    def _disc_out(disc: dict) -> dict:
        out = {}
        for ln in disc_keys:
            entry = {}
            for h in DISCRIM_HOLDS:
                w = disc[ln][h]["wash"]
                b = disc[ln][h]["break"]
                entry[str(h)] = {
                    "wash": {"n": w[0], "avg_return": round(w[1] / w[0], 6) if w[0] else 0.0,
                             "win_rate": round(w[2] / w[0], 6) if w[0] else 0.0},
                    "break": {"n": b[0], "avg_return": round(b[1] / b[0], 6) if b[0] else 0.0,
                              "win_rate": round(b[2] / b[0], 6) if b[0] else 0.0},
                }
            out[ln] = entry
        return out
    result["discrimination"] = _disc_out(disc_2day)
    result["discrimination_1day"] = _disc_out(disc_1day)

    del candles
    gc.collect()
    return result


def _fmt_stat(d: dict, mode: str) -> str:
    star = "*" if d.get("insufficient") else ""
    if mode == "fixed":
        return "%s%.0f/%+.2f|%+.1f/%+.2f(%.1f/%.1f)(%d)" % (
            star, d["win_rate"] * 100, d["avg_return"] * 100,
            d["excess_win_rate"] * 100, d["excess_return"] * 100,
            d["mae_mean"] * 100, d["mfe_mean"] * 100, d["n"])
    return "%s%.0f/%+.2f(%.1f/%.1f,持%.0f,换%.1f)(%d)" % (
        star, d["win_rate"] * 100, d["avg_return"] * 100,
        d["mae_mean"] * 100, d["mfe_mean"] * 100,
        d["avg_holding_days"], d["avg_turnover"], d["n"])


def print_report(results: dict) -> None:
    labels = [l for l in ("IS", "OOS-A", "OOS-B", "OOS-C") if l in results]

    print("\n" + "=" * 130)
    print("第二步：三组对照（固定 25/60 持有；仓位循环）—— 胜率% / 绝对收益% | 超额胜率pp/超额收益% (MAE%/MFE%) (n)")
    print("=" * 130)
    for h in FIXED_HOLDS:
        print("\n  持有 %d 日：" % h)
        hdr = "      %-14s" % "组"
        for l in labels:
            hdr += "%30s" % l
        print(hdr)
        for grp, name in (("g1", "纯单针(深水)"), ("g2", "单针+阶段底")):
            row = "      %-14s" % name
            for l in labels:
                row += "%30s" % _fmt_stat(results[l][grp][str(h)], "fixed")
            print(row)
        bl = "      %-14s" % "基线"
        for l in labels:
            b = results[l]["baselines"][str(h)]
            bl += "%30s" % ("%.1f/%+.2f" % (b["win_rate"] * 100, b["avg_return"] * 100))
        print(bl)

    print("\n" + "=" * 130)
    print("组3/第四步：完整架构仓位循环（3-2-2-1 + 阶段顶卖50% + 洗盘加仓）—— 胜率% / 绝对收益% (MAE/MFE,持有日,换手) (n)")
    print("=" * 130)
    hdr = "      %-14s" % "组"
    for l in labels:
        hdr += "%34s" % l
    print(hdr)
    row = "      %-14s" % "完整架构"
    for l in labels:
        row += "%34s" % _fmt_stat(results[l]["g3"], "pos")
    print(row)
    print("\n  对照（同一入场，买入持有到期末）：")
    hdr = "      %-14s" % "口径"
    for l in labels:
        hdr += "%24s" % l
    print(hdr)
    for name, key in (("满仓持有", "buy_hold_full"), ("固定50%", "buy_hold_half")):
        row = "      %-14s" % name
        for l in labels:
            row += "%24s" % ("%+.2f%%" % (results[l]["g3"][key] * 100))
        print(row)

    print("\n" + "=" * 130)
    print("第三步：三条线作为洗盘判别器——组A(回踩不破=洗盘) vs 组B(已破2日=破位) 前向收益差")
    print("=" * 130)
    for ln in LINES + ["any", "all"]:
        name = LINE_NAMES.get(ln, ("任一不破" if ln == "any" else "全部不破"))
        print("\n  【%s】" % name)
        hdr = "      %-8s" % "持有"
        for l in labels:
            hdr += "%34s" % l
        print(hdr)
        for h in DISCRIM_HOLDS:
            row = "      %-8s" % ("%d日" % h)
            for l in labels:
                c = results[l]["discrimination"][ln][str(h)]
                w = c["wash"]
                b = c["break"]
                diff = (w["avg_return"] - b["avg_return"]) * 100
                row += "%34s" % ("A洗盘%+.2f(%d) B破位%+.2f(%d) Δ%+.2f" % (
                    w["avg_return"] * 100, w["n"], b["avg_return"] * 100, b["n"], diff))
            print(row)
    print("\n" + "=" * 130)
    print("对照：单日破即算破（无 2 日容错）的判别器 Δ（组A洗盘 - 组B破位，25/60 日）——量化容错收益差")
    print("=" * 130)
    for ln in LINES + ["any", "all"]:
        name = LINE_NAMES.get(ln, ("任一不破" if ln == "any" else "全部不破"))
        row = "  %-8s" % name
        for h in (25, 60):
            row += " | %d日: " % h
            for l in labels:
                if "discrimination_1day" not in results[l]:
                    continue
                c = results[l]["discrimination_1day"][ln][str(h)]
                w = c["wash"]
                b = c["break"]
                diff = (w["avg_return"] - b["avg_return"]) * 100
                row += "%s %+.2f " % (l, diff)
        print(row)


def main() -> None:
    ap = argparse.ArgumentParser(description="阶段14 柱状阶段顶底+三条线判别器 四段验证")
    ap.add_argument("--windows", nargs="+", default=["IS", "A", "B", "C"])
    ap.add_argument("--out", default="data/stage14_backtest.json")
    ap.add_argument("--limit", type=int, default=None, help="只跑前 N 只（烟囱测试）")
    args = ap.parse_args()

    out_path = Path(args.out)
    results: dict = {}
    if out_path.exists():
        try:
            results = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            results = {}

    for window in args.windows:
        results[WINDOW_LABELS[window]] = run_window(window, limit=args.limit)
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print_report(results)
    print("\n结构化快照已写入 %s" % out_path)


if __name__ == "__main__":
    main()
