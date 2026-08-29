#!/usr/bin/env python3
"""阶段 12b：pin30 深水单针——带止损的持有（stop-loss holding）重测。

## 背景

阶段 12b 分桶表（run_pin30_band_holds.py）显示深水单针（桶3）40/60 日超额正但 MAE
很深（25 日 -13%、60 日 -22%），「扛不住」。Jeremy 的口径：**不是扛浮亏，是止损**——
「买入后 2-5 天内一直下跌，跌破阴量定价线或生命线就卖；等市场消化一下底部再买」。

## 止损规则（复用 indicators/divergence，已确认时点无前视）

逐日收盘触发「收盘 < 线」即止损：
- **条件A 生命线** divergence_midline = (最近已确认顶背离高点 + 最近已确认底背离低点)/2
- **条件B 阴量定价线** yin_volume_line，两处未定全部实现做 A/B：
  - 锚点：V1 = 顶背离高点后第一根「放量阴线」（放量=量 > 1.2×20 日均量）；
          V2 = 背离区间 [i1,i2] 内成交量最大的阴线（= 规格「阴线+量最大」原定义）
  - 取价：P1 = 该阴线最高价；P2 = 实体顶（开盘价）
  - 4 组合：V1P1 / V1P2 / V2P1 / V2P2
- 触发窗口：主口径「买入后 5 日内跌破即止损」；对照「全持有期内任意时点跌破即止损」
- 止损后冷却：5 / 10 日，冷却结束后若再现深水单针则重新买入（测再买胜率）

## 对比

1. 无止损固定持有（5/13/25/60，同桶3 基线）
2. 带止损（生命线单用 / 阴量线单用 4 变体 / 生命线∪阴量线任一触发）
每组：胜率 / 平均收益（绝对+超额分列）/ MAE 均值+中位数 / 被止损比例 / 止损后再买胜率。

## 口径与简化（写死进报告）

- 入场 = 桶3 深水单针基础事件（short<=30 且 非趋势多头 且 long<=55），与分桶表同。
- 止损线在信号日 i 用「已确认背离」（confirmed_bar <= i）计算，无前视。
- 生命线需「最近已确认顶背离」+「最近已确认底背离」同时存在才定义；阴量线需顶背离存在。
- 止损成交在触发日收盘价；未触发则持有到 i+H 收盘。忽略交易成本、现金零收益。
- 「任一触发」= 收盘跌破 max(生命线, 阴量线)（下跌先破较高那条）。
- 无止损对照用同一「线已定义」的子集（同子集公平比）。

用法（仓库根目录）：
    .venv/bin/python scripts/run_pin30_stoploss.py --windows IS A B C \
        --out data/pin30_stoploss.json
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
from indicators.divergence import detect_bearish_divergences, detect_bullish_divergences
from indicators.macd import calc_macd
from indicators.rsi import calc_rsi
from strategies.filters import SymbolKind
from strategies.pin30.config import default_config as pin30_default_config

from scripts.pin30_common import pin30_series
from scripts.run_oos_strategies import WINDOW_LABELS, WINDOWS, load_universe, peak_rss_mb

HOLDS = [5, 13, 25, 60]
SHORT_PIN = 30.0
LONG_DEEP_MAX = 55.0
DIV_K = 6
FANG_LIANG_RATIO = 1.2  # 放量阴线：量 > 1.2 × 20 日均量
MIN_N = 100
WARMUP_BARS = 320

# 止损规则：生命线 / 阴量线 4 变体 / 任一触发（用规格原定义 V2P1 作代表）
RULES = ["lifeline", "yin_v1p1", "yin_v1p2", "yin_v2p1", "yin_v2p2", "either_v2p1"]
RULE_NAMES = {
    "lifeline": "生命线 单用",
    "yin_v1p1": "阴量线 V1P1（高点后首根放量阴线·最高价）",
    "yin_v1p2": "阴量线 V1P2（高点后首根放量阴线·实体顶）",
    "yin_v2p1": "阴量线 V2P1（区间量最大阴线·最高价）",
    "yin_v2p2": "阴量线 V2P2（区间量最大阴线·实体顶）",
    "either_v2p1": "生命线 ∪ 阴量线V2P1（任一触发）",
}

TRIGGERS = {"5d": 5, "full": None}  # None = 全持有期 H

# 诊断用板块归类（申万 → T0/T1/T2 启发式）
T0_SECTORS = {"BK1201", "BK1207", "BK1215"}  # 电子/计算机/通信 = AI/半导体
T1_SECTORS = {"BK1200"}  # 电力设备 = 光伏/新能源


def load_sector_tier() -> dict[str, str]:
    """code -> T0/T1/T2（按申万行业启发式归类）。"""
    d = json.loads((ROOT / "data" / "sector_members.json").read_text(encoding="utf-8"))
    sec_of_code: dict[str, str] = {}
    for bk, sec in d["sectors"].items():
        for m in sec["members"]:
            sec_of_code.setdefault(m["code"], bk)
    tier: dict[str, str] = {}
    for code, bk in sec_of_code.items():
        if bk in T0_SECTORS:
            tier[code] = "T0"
        elif bk in T1_SECTORS:
            tier[code] = "T1"
        else:
            tier[code] = "T2"
    return tier


def _rolling_mean(values: np.ndarray, period: int) -> np.ndarray:
    csum = np.concatenate(([0.0], np.cumsum(values)))
    i = np.arange(len(values))
    s = np.maximum(0, i - period + 1)
    return (csum[i + 1] - csum[s]) / (i - s + 1)


def _sma(values: np.ndarray, period: int) -> np.ndarray:
    return _rolling_mean(values, period)


def build_flags(df) -> dict:
    """单标的：所有指标数组 + 已确认背离前向填充（无前视）。"""
    s = pin30_series(df)
    closes = s["close"]
    n = len(closes)
    short = s["short"]
    long_ = s["long"]
    trend = s["trend"]

    closes_l = closes.tolist()
    highs = df["high"].astype(float).to_numpy()
    lows = df["low"].astype(float).to_numpy()
    opens = df["open"].astype(float).to_numpy()
    vols = df["volume"].astype(float).to_numpy()
    amounts = df["amount"].astype(float).to_numpy()

    dif, _dea, hist = calc_macd(closes_l)
    rsi = calc_rsi(closes_l)
    dif = np.asarray(dif, dtype=float)
    hist = np.asarray(hist, dtype=float)
    rsi = np.asarray(rsi, dtype=float)

    is_yin = closes < opens
    vol_ma20 = _rolling_mean(vols, 20)
    fang_liang = vols > FANG_LIANG_RATIO * vol_ma20
    fang_liang_yin = is_yin & fang_liang

    # 顶背离 → 最近已确认高点的前向填充
    bear = detect_bearish_divergences(highs.tolist(), dif.tolist(), hist.tolist(), k=DIV_K)
    bear_high = np.zeros(n)
    bear_i1 = np.full(n, -1, dtype=int)
    bear_i2 = np.full(n, -1, dtype=int)
    bear_v2j = np.full(n, -1, dtype=int)
    bear_has = np.zeros(n, dtype=bool)
    for d in sorted(bear, key=lambda x: x.confirmed_bar):
        cb = d.confirmed_bar
        if cb >= n:
            continue
        # V2 = 区间 [i1,i2] 内成交量最大的阴线
        seg = np.arange(d.i1, d.i2 + 1)
        yin = seg[is_yin[seg]]
        v2j = int(yin[np.argmax(vols[yin])]) if yin.size else -1
        bear_high[cb:] = d.p2
        bear_i1[cb:] = d.i1
        bear_i2[cb:] = d.i2
        bear_v2j[cb:] = v2j
        bear_has[cb:] = True

    # 底背离 → 最近已确认低点
    bull = detect_bullish_divergences(lows.tolist(), dif.tolist(), hist.tolist(), rsi.tolist(), k=DIV_K)
    bull_low = np.zeros(n)
    bull_has = np.zeros(n, dtype=bool)
    for d in sorted(bull, key=lambda x: x.confirmed_bar):
        cb = d.confirmed_bar
        if cb >= n:
            continue
        bull_low[cb:] = d.p2
        bull_has[cb:] = True

    # next 放量阴线索引（V1 用）：next_fly[j] = 第一个 >= j 的放量阴线，无则 n
    fly_pos = np.flatnonzero(fang_liang_yin)
    idx = np.searchsorted(fly_pos, np.arange(n), side="left")
    next_fly = np.where(idx < fly_pos.size, fly_pos[np.minimum(idx, fly_pos.size - 1)], n)

    return {
        "close": closes, "high": highs, "low": lows, "open": opens,
        "volume": vols, "amount": amounts,
        "short": short, "long": long_, "trend": trend,
        "is_yin": is_yin, "fang_liang_yin": fang_liang_yin, "next_fly": next_fly,
        "bear_high": bear_high, "bear_i1": bear_i1, "bear_i2": bear_i2,
        "bear_v2j": bear_v2j, "bear_has": bear_has,
        "bull_low": bull_low, "bull_has": bull_has,
        "vol_ma20": vol_ma20, "ma10": _sma(closes, 10),
        "amount_ma20": _rolling_mean(amounts, 20),
    }


def stop_levels(fl: dict, i: int) -> dict[str, float | None]:
    """信号日 i 的各止损线（None = 该线未定义）。"""
    out: dict[str, float | None] = {}
    bh = fl["bear_high"][i]
    bl = fl["bull_low"][i]
    has_bear = bool(fl["bear_has"][i])
    has_bull = bool(fl["bull_has"][i])
    # 生命线
    out["lifeline"] = (bh + bl) / 2.0 if (has_bear and has_bull and bh > 0 and bl > 0) else None
    # 阴量线
    yin = {k: None for k in ("yin_v1p1", "yin_v1p2", "yin_v2p1", "yin_v2p2")}
    if has_bear:
        i1 = fl["bear_i1"][i]
        i2 = fl["bear_i2"][i]
        # V1：i2 之后第一根放量阴线，且 <= i（无前视）
        v1j = int(fl["next_fly"][i2 + 1]) if i2 + 1 < len(fl["close"]) else -1
        if v1j != -1 and v1j <= i and v1j != len(fl["close"]):
            yin["yin_v1p1"] = float(fl["high"][v1j])
            yin["yin_v1p2"] = float(fl["open"][v1j])
        # V2：区间内量最大阴线
        v2j = int(fl["bear_v2j"][i])
        if v2j != -1:
            yin["yin_v2p1"] = float(fl["high"][v2j])
            yin["yin_v2p2"] = float(fl["open"][v2j])
    out.update(yin)
    # 任一触发 = max(生命线, 阴量线V2P1)
    if out["lifeline"] is not None and out["yin_v2p1"] is not None:
        out["either_v2p1"] = max(out["lifeline"], out["yin_v2p1"])
    elif out["lifeline"] is not None:
        out["either_v2p1"] = out["lifeline"]
    elif out["yin_v2p1"] is not None:
        out["either_v2p1"] = out["yin_v2p1"]
    else:
        out["either_v2p1"] = None
    return out


class Accum:
    """运行累加：ret 用运行和（胜率/均值），只存 MAE（供中位数），内存友好。"""

    def __init__(self):
        self.mae = array("d")
        self.n = 0
        self.win = 0
        self.sum_ret = 0.0
        self.stopped = 0

    def add(self, ret: float, mae: float, stopped: bool):
        self.mae.append(mae)
        self.n += 1
        if ret > 0:
            self.win += 1
        self.sum_ret += ret
        if stopped:
            self.stopped += 1


def _stat(acc: Accum, base_win: float, base_ret: float) -> dict:
    n = acc.n
    win = acc.win / n if n else 0.0
    avg = acc.sum_ret / n if n else 0.0
    m = np.frombuffer(acc.mae, dtype=np.float64) if n else np.empty(0)
    return {
        "n": n,
        "win_rate": round(win, 6),
        "avg_return": round(avg, 6),
        "excess_win_rate": round(win - base_win, 6),
        "excess_return": round(avg - base_ret, 6),
        "mae_mean": round(float(m.mean()), 6) if m.size else 0.0,
        "mae_median": round(float(np.median(m)), 6) if m.size else 0.0,
        "stopped_ratio": round(acc.stopped / n, 6) if n else 0.0,
        "insufficient": n < MIN_N,
    }


def run_window(window: str, tier: dict[str, str]) -> dict:
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
    H_MAX = max(HOLDS)

    # 累加器：no_stop[rule][H] 与 stop[rule][H][trigger]
    no_stop: dict[str, dict[int, Accum]] = {r: {h: Accum() for h in HOLDS} for r in RULES}
    stop: dict[str, dict[int, dict[str, Accum]]] = {
        r: {h: {t: Accum() for t in TRIGGERS} for h in HOLDS} for r in RULES
    }
    # 线相对入场价的分布（线价/收盘价 - 1，正值=线在入场价上方）
    line_offsets: dict[str, array] = {r: array("d") for r in RULES}
    # 诊断：代表性规则（either_v2p1, 5d, H=25）止/不止损两组在信号日的特征
    diag_stopped: dict[str, list] = {"vol_ratio": [], "dev_ma10": [], "long": [], "tier": []}
    diag_held: dict[str, list] = {"vol_ratio": [], "dev_ma10": [], "long": [], "tier": []}
    diag_rule = "either_v2p1"
    diag_h = 25
    diag_trigger = "5d"
    # 再买（冷却 5/10 日）后下一深水单针的 25/60 日收益
    rebuy: dict[int, dict[int, Accum]] = {cd: {h: Accum() for h in (25, 60)} for cd in (5, 10)}

    # 再买：per symbol 入口索引（用于冷却后再买胜率）
    # 简化：逐 symbol 收集入口，止损后再买在 symbol 内 searchsorted

    t0 = time.time()
    n_done = 0
    n_entries = 0
    for symbol in symbols:
        df = candles[symbol]
        n = len(df)
        if n < min_bars:
            continue
        fl = build_flags(df)
        close = fl["close"]
        low = fl["low"]
        ordinals = np.array([d.toordinal() for d in df["date"].to_numpy()], dtype=np.int64)
        i0 = int(np.searchsorted(ordinals, start_ord, side="left"))
        i1 = int(np.searchsorted(ordinals, end_ord, side="right"))

        # 桶3 入口索引（全窗口，且 i + H_MAX < n）
        idx = np.arange(i0, i1)
        if idx.size == 0:
            continue
        mask = (fl["short"][idx] <= SHORT_PIN) & (~fl["trend"][idx]) & (fl["long"][idx] <= LONG_DEEP_MAX) & (idx >= min_bars - 1) & (idx + H_MAX < n)
        entries = idx[mask]
        if entries.size == 0:
            n_done += 1
            continue
        n_entries += entries.size

        rep_stop_days: list[int] = []

        for i in entries:
            ci = close[i]
            if ci <= 0:
                continue
            levels = stop_levels(fl, i)
            # 无止损 forward 与 MAE（一次性算，各 H）
            for h in HOLDS:
                j = i + h
                r_ns = close[j] / ci - 1.0
                m_ns = low[i + 1 : i + h + 1].min() / ci - 1.0
                for r in RULES:
                    if levels[r] is not None:
                        no_stop[r][h].add(r_ns, m_ns, False)
            # 带止损
            for r in RULES:
                L = levels[r]
                if L is None:
                    continue
                line_offsets[r].append(L / ci - 1.0)
                for h in HOLDS:
                    # 首个收盘 < L 的偏移（0 基，i+1 为偏移 0）
                    win_close = close[i + 1 : i + h + 1]
                    cross = np.flatnonzero(win_close < L)
                    for tname, twin in TRIGGERS.items():
                        limit = twin if twin is not None else h
                        if cross.size and cross[0] < limit:
                            k = int(cross[0])
                            r_s = win_close[k] / ci - 1.0
                            m_s = low[i + 1 : i + k + 2].min() / ci - 1.0
                            stop[r][h][tname].add(r_s, m_s, True)
                        else:
                            r_s = close[i + h] / ci - 1.0
                            m_s = low[i + 1 : i + h + 1].min() / ci - 1.0
                            stop[r][h][tname].add(r_s, m_s, False)
            # 诊断（代表性规则 either_v2p1, 5d, H=25）
            if levels[diag_rule] is not None:
                Ld = levels[diag_rule]
                win_close = close[i + 1 : i + diag_h + 1]
                cross = np.flatnonzero(win_close < Ld)
                stopped = bool(cross.size and cross[0] < 5)
                if stopped:
                    rep_stop_days.append(int(i) + 1 + int(cross[0]))
                vol_ratio = float(fl["volume"][i] / fl["vol_ma20"][i]) if fl["vol_ma20"][i] > 0 else 0.0
                dev = float((close[i] - fl["ma10"][i]) / fl["ma10"][i]) if fl["ma10"][i] > 0 else 0.0
                lg = float(fl["long"][i])
                tg = tier.get(symbol, "T2")
                tgt = diag_stopped if stopped else diag_held
                tgt["vol_ratio"].append(vol_ratio)
                tgt["dev_ma10"].append(dev)
                tgt["long"].append(lg)
                tgt["tier"].append(tg)

        # 止损后再买：代表规则(任一触发,5日窗)被止损的，冷却后下一深水单针再买
        for sd in rep_stop_days:
            for cd in (5, 10):
                nxt = int(np.searchsorted(entries, sd + cd, side="right"))
                if nxt < entries.size:
                    j = int(entries[nxt])
                    for h in (25, 60):
                        rebuy[cd][h].add(
                            float(close[j + h] / close[j] - 1.0),
                            float(low[j + 1 : j + h + 1].min() / close[j] - 1.0),
                            False,
                        )

        n_done += 1
        if n_done % 1000 == 0:
            gc.collect()
            print("    ...%d/%d 只，入口 %d，%.1fs，RSS峰值 %.0fMB" % (n_done, len(symbols), n_entries, time.time() - t0, peak_rss_mb()), flush=True)

    print("  模拟完成，%d 只，入口 %d，%.1fs" % (n_done, n_entries, time.time() - t0), flush=True)

    # 基线（个股宇宙，同持有期）
    base = compute_baseline(candles, symbols, "stock", start, end, HOLDS)
    baselines = {str(h.hold_days): {"win_rate": h.win_rate, "avg_return": h.avg_return} for h in base.holds}

    result: dict = {"window": label, "start": str(start), "end": str(end), "n_entries": n_entries}
    result["baselines"] = baselines
    result["rules"] = {}
    for r in RULES:
        entry = {"name": RULE_NAMES[r], "holds": {}}
        for h in HOLDS:
            bw = baselines[str(h)]["win_rate"]
            br = baselines[str(h)]["avg_return"]
            hs = {
                "no_stop": _stat(no_stop[r][h], bw, br),
                "triggers": {t: _stat(stop[r][h][t], bw, br) for t in TRIGGERS},
            }
            entry["holds"][str(h)] = hs
        off = np.asarray(line_offsets[r], dtype=float) if line_offsets[r] else np.empty(0)
        entry["line_offset"] = {
            "n": int(off.size),
            "mean": round(float(off.mean()), 6) if off.size else 0.0,
            "median": round(float(np.median(off)), 6) if off.size else 0.0,
            "below_entry_frac": round(float((off < 0).mean()), 6) if off.size else 0.0,  # 线在入场价下方=真支撑
        }
        result["rules"][r] = entry

    def _diag_stat(d: dict) -> dict:
        out = {}
        for k in ("vol_ratio", "dev_ma10", "long"):
            a = np.asarray(d[k], dtype=float) if d[k] else np.empty(0)
            out[k] = {
                "n": int(a.size),
                "mean": round(float(a.mean()), 4) if a.size else 0.0,
                "median": round(float(np.median(a)), 4) if a.size else 0.0,
            }
        tiers = d["tier"]
        out["tier"] = {t: tiers.count(t) for t in ("T0", "T1", "T2")}
        return out

    result["diagnostic"] = {
        "rule": RULE_NAMES[diag_rule],
        "hold": diag_h,
        "trigger": diag_trigger,
        "stopped": _diag_stat(diag_stopped),
        "held": _diag_stat(diag_held),
    }
    result["rebuy"] = {
        str(cd): {
            str(h): _stat(rebuy[cd][h], baselines[str(h)]["win_rate"], baselines[str(h)]["avg_return"])
            for h in (25, 60)
        }
        for cd in (5, 10)
    }

    del candles
    gc.collect()
    return result


def print_report(results: dict) -> None:
    labels = [l for l in ("IS", "OOS-A", "OOS-B", "OOS-C") if l in results]
    for h in HOLDS:
        print("\n" + "=" * 130)
        print("持有 %d 日：无止损 vs 带止损（5日窗/全窗）—— 胜率%% / 平均收益%%(绝对) / MAE均值%% / 被止损%% | 超额胜率/超额收益" % h)
        print("=" * 130)
        hdr = "    %-40s" % "规则"
        for l in labels:
            hdr += "%24s" % l
        print(hdr)
        for r in RULES:
            # 无止损
            row = "    %-40s" % ("[无止损] " + RULE_NAMES[r][:28])
            for l in labels:
                c = results[l]["rules"][r]["holds"][str(h)]["no_stop"]
                row += "%24s" % ("%s%.0f/%+.2f/%.1f/-|%+.1f/%+.2f" % (
                    "*" if c["insufficient"] else "", c["win_rate"] * 100, c["avg_return"] * 100,
                    c["mae_mean"] * 100, c["excess_win_rate"] * 100, c["excess_return"] * 100))
            print(row)
            for tname, tlabel in (("5d", "5日窗"), ("full", "全窗")):
                row = "    %-40s" % ("[%s] %s" % (tlabel, RULE_NAMES[r][:28]))
                for l in labels:
                    c = results[l]["rules"][r]["holds"][str(h)]["triggers"][tname]
                    row += "%24s" % ("%s%.0f/%+.2f/%.1f/%.0f|%+.1f/%+.2f" % (
                        "*" if c["insufficient"] else "", c["win_rate"] * 100, c["avg_return"] * 100,
                        c["mae_mean"] * 100, c["stopped_ratio"] * 100,
                        c["excess_win_rate"] * 100, c["excess_return"] * 100))
                print(row)
        bl = "    %-40s" % "[基线 胜率%/均值%]"
        for l in labels:
            b = results[l]["baselines"][str(h)]
            bl += "%24s" % ("%.1f / %+.2f" % (b["win_rate"] * 100, b["avg_return"] * 100))
        print(bl)

    # 线相对入场价分布
    print("\n" + "=" * 130)
    print("止损线相对入场价（线价/收盘价-1；正值=线在上方，负值=线是入场价下方真支撑）")
    print("=" * 130)
    hdr = "    %-40s" % "规则"
    for l in labels:
        hdr += "%24s" % l
    print(hdr)
    for r in RULES:
        row = "    %-40s" % RULE_NAMES[r]
        for l in labels:
            o = results[l]["rules"][r]["line_offset"]
            row += "%24s" % ("%+.1f%%(下%.0f%%)" % (o["mean"] * 100, o["below_entry_frac"] * 100))
        print(row)

    # 再买胜率
    print("\n" + "=" * 130)
    print("止损后再买（代表规则=任一触发,5日窗；冷却 5/10 日后下一深水单针）—— 胜率% / 平均收益%(绝对) / 超额")
    print("=" * 130)
    hdr = "    %-24s" % "再买口径"
    for l in labels:
        hdr += "%24s" % l
    print(hdr)
    for cd in (5, 10):
        for h in (25, 60):
            row = "    %-24s" % ("冷却%d日 持有%d日" % (cd, h))
            for l in labels:
                c = results[l]["rebuy"][str(cd)][str(h)]
                row += "%24s" % ("%s%.0f/%+.2f/%+.1f" % (
                    "*" if c["insufficient"] else "", c["win_rate"] * 100,
                    c["avg_return"] * 100, c["excess_win_rate"] * 100))
            print(row)

    # 诊断：止/不止损两组信号日特征
    print("\n" + "=" * 130)
    print("诊断：被止损 vs 未被止损 在信号日的特征（代表规则=任一触发,5日窗,持有25日）")
    print("=" * 130)
    for l in labels:
        d = results[l]["diagnostic"]
        print("\n  【%s】" % l)
        for grp in ("stopped", "held"):
            g = d[grp]
            tier = g["tier"]
            tot = sum(tier.values()) or 1
            print("    %-8s 量比%.2f/%.2f  偏离度%+.1f%%/%+.1f%%  长期%.1f/%.1f  T0%.0f%% T1%.0f%% T2%.0f%% (n=%d)" % (
                "被止损" if grp == "stopped" else "未止损",
                g["vol_ratio"]["mean"], g["vol_ratio"]["median"],
                g["dev_ma10"]["mean"] * 100, g["dev_ma10"]["median"] * 100,
                g["long"]["mean"], g["long"]["median"],
                tier.get("T0", 0) / tot * 100, tier.get("T1", 0) / tot * 100, tier.get("T2", 0) / tot * 100,
                g["vol_ratio"]["n"],
            ))


def main() -> None:
    ap = argparse.ArgumentParser(description="pin30 深水单针 带止损持有重测")
    ap.add_argument("--windows", nargs="+", default=["IS", "A", "B", "C"])
    ap.add_argument("--out", default="data/pin30_stoploss.json")
    args = ap.parse_args()

    tier = load_sector_tier()

    out_path = Path(args.out)
    results: dict = {}
    if out_path.exists():
        try:
            results = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            results = {}

    for window in args.windows:
        results[WINDOW_LABELS[window]] = run_window(window, tier)
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print_report(results)
    print("\n结构化快照已写入 %s" % out_path)


if __name__ == "__main__":
    main()
