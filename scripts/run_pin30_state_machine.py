#!/usr/bin/env python3
"""pin30 仓位状态机（阶段 12 任务 2）：顶背离降仓 + 深水单针加仓 vs 买入持有。

## 背景

Jeremy 的仓位纪律（2026-08-29 纠正版）：下跌趋势里底仓不可能有 70%。这是一套
**仓位状态机**，不是静态 70/30 配比：

    - 状态A 上升趋势（趋势多头）：仓位高位运行，原始单针（短≤30+长≥80）触发回踩加仓
    - 状态B 顶部确认（顶背离）：分批降仓到 10~30% 底仓（慢慢降，不是一次清仓）
    - 状态C 下跌趋势（非趋势多头）：维持底仓，深水单针（短≤30 且 长≤55 + 底背离
      二次探底 + 增量资金 + 不破底）触发时博反弹加仓
    - 状态C 再遇顶背离 → 卖回底仓；循环往复

## 本脚本做什么

对每只个股，逐日模拟仓位状态机（顶背离 → 降到底仓；单针 → 加仓），与两个基准
（买入持有满仓 100%、固定 50% 不动）对比最终收益 / 最大回撤 / 夏普 / 卡玛 /
平均仓位 / 换手次数。指标在**个股层面**算，再在宇宙上取均值 / 中位数（等权）。

参数网格（全部落盘）：
    - 底仓下限 base ∈ {10%, 20%, 30%}
    - 加仓幅度 add_mode ∈ {+30pp（如 20%→50%）, ×1.3（20%→26%）}
    - 上限 cap ∈ {70%, 100%}
    - 减仓节奏 reduce_mode ∈ {一次到底仓, 分步（确认日降一半，5 日后到底仓）}

## 口径与简化（写死在报告里）

- 顶背离：indicators.divergence.detect_bearish_divergences（pivot high 各 k=6 根，
  价格创新高/齐平但 DIF 走低），已确认时点 = 右 pivot + k 根（无前视）。
- 底背离二次探底：detect_bullish_divergences（double_bottom 口径，DIF/柱/RSI 三取二、
  DIF 硬条件）。「不破底」= 信号日收盘未跌破右底 × 0.97。
- 增量资金：当日成交额 > 1.2 × 20 日均成交额。
- 建仓/减仓在信号日收盘生效（对次日收益生效）；忽略交易成本；现金零收益。
- 窗口内日线按个股自身 bar 对齐，停牌/新上市前向填充（自然处理）。

用法（仓库根目录）：
    .venv/bin/python scripts/run_pin30_state_machine.py --windows IS A B C \
        --out data/pin30_state_machine.json
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

from indicators.divergence import detect_bearish_divergences, detect_bullish_divergences
from indicators.macd import calc_macd
from indicators.rsi import calc_rsi
from strategies.filters import SymbolKind
from strategies.pin30.config import default_config as pin30_default_config

from scripts.pin30_common import pin30_series
from scripts.run_oos_strategies import WINDOW_LABELS, WINDOWS, load_universe, peak_rss_mb

WARMUP_BARS = 320
MIN_N = 100

# 触发阈值（集中于此，不做搜索）
SHORT_PIN = 30.0  # 单针：短期随机 <= 30
LONG_ORIG_MIN = 80.0  # 原始单针：长期 >= 80
LONG_DEEP_MAX = 55.0  # 深水：长期 <= 55
MONEY_IN_RATIO = 1.2  # 增量资金：成交额 > 1.2 × 20 日均额
SUPPORT_BREAK = 0.97  # 不破底：收盘 >= 右底 × 0.97
DIV_K = 6  # pivot 各 6 根
DIV_RECENT = 40  # 底背离右底需在最近 40 根内才算「新鲜」

# 参数网格
BASES = [0.10, 0.20, 0.30]
ADD_MODES = ["pp30", "rel30"]
CAPS = [0.70, 1.00]
REDUCE_MODES = ["once", "gradual"]

# 默认配置（详细报表用）
DEFAULT_PARAMS = {"base": 0.20, "add_mode": "pp30", "cap": 1.00, "reduce_mode": "gradual"}

GRADUAL_STEP_BARS = 5  # 分步降仓：确认日降一半，之后每 5 根（交易日）再降一次


def _sharpe(daily_returns: np.ndarray) -> float:
    if len(daily_returns) < 2:
        return 0.0
    sd = float(daily_returns.std())
    if sd <= 0:
        return 0.0
    return float(daily_returns.mean() / sd * np.sqrt(252.0))


def _max_drawdown(equity: np.ndarray) -> float:
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = 1.0 - equity / np.where(peak > 0, peak, 1.0)
    return float(dd.max())


def _calmar(ret: float, mdd: float) -> float:
    return ret / mdd if mdd > 1e-9 else 0.0


def _rolling_mean_series(values: np.ndarray, period: int) -> np.ndarray:
    csum = np.concatenate(([0.0], np.cumsum(values)))
    i = np.arange(len(values))
    s = np.maximum(0, i - period + 1)
    return (csum[i + 1] - csum[s]) / (i - s + 1)


def build_flags(df, cfg) -> dict:
    """对单只标的算状态机所需的全部 flag 数组（在窗口索引 i0..i1 上取值）。"""
    s = pin30_series(df)
    closes = s["close"]
    n = len(closes)
    short = s["short"]
    long_ = s["long"]
    trend = s["trend"]

    closes_l = closes.tolist()
    highs_l = df["high"].astype(float).tolist()
    lows_l = df["low"].astype(float).tolist()
    dif, _dea, hist = calc_macd(closes_l)
    rsi = calc_rsi(closes_l)
    amounts = df["amount"].astype(float).to_numpy()

    dif = np.asarray(dif, dtype=float)
    hist = np.asarray(hist, dtype=float)
    rsi = np.asarray(rsi, dtype=float)
    lows = np.asarray(lows_l, dtype=float)
    highs = np.asarray(highs_l, dtype=float)

    # 顶背离确认日
    top_div = np.zeros(n, dtype=bool)
    for d in detect_bearish_divergences(highs_l, dif.tolist(), hist.tolist(), k=DIV_K):
        if d.confirmed_bar < n:
            top_div[d.confirmed_bar] = True

    # 底背离确认 → 活动支撑位（不破底）
    bull = detect_bullish_divergences(lows_l, dif.tolist(), hist.tolist(), rsi.tolist(), k=DIV_K)
    support = np.zeros(n, dtype=float)
    recent_bottom_div = np.zeros(n, dtype=bool)
    if bull:
        # 按 confirmed_bar 建立「最近已确认右底」的支撑，前向填充，破位归零
        events = sorted(bull, key=lambda d: d.confirmed_bar)
        cur_support = 0.0
        cur_i2 = -10**9
        ev_idx = 0
        for t in range(n):
            while ev_idx < len(events) and events[ev_idx].confirmed_bar <= t:
                cur_support = events[ev_idx].p2  # 右底低点
                cur_i2 = events[ev_idx].i2
                ev_idx += 1
            if cur_support > 0 and closes[t] < cur_support * SUPPORT_BREAK:
                cur_support = 0.0
                cur_i2 = -10**9
            support[t] = cur_support
            recent_bottom_div[t] = cur_support > 0 and (t - cur_i2) <= DIV_RECENT

    # 增量资金：成交额 > 1.2 × 20 日均额
    amount_ma20 = _rolling_mean_series(amounts, 20)
    money_in = amounts > MONEY_IN_RATIO * amount_ma20

    # 原始单针（状态A 回踩加仓）
    add_orig = trend & (short <= SHORT_PIN) & (long_ >= LONG_ORIG_MIN)
    # 深水单针（状态C 博反弹加仓）
    add_deep = (
        (~trend)
        & (short <= SHORT_PIN)
        & (long_ <= LONG_DEEP_MAX)
        & money_in
        & recent_bottom_div
    )
    add_flag = add_orig | add_deep

    return {
        "close": closes,
        "top_div": top_div,
        "add_flag": add_flag,
        "add_orig": add_orig,
        "add_deep": add_deep,
    }


def simulate_position(flags: dict, i0: int, i1: int, params: dict) -> dict:
    """对单只标的在窗口 [i0, i1] 上跑状态机，返回净值曲线与指标。"""
    close = flags["close"]
    top_div = flags["top_div"]
    add_flag = flags["add_flag"]

    base = params["base"]
    cap = params["cap"]
    add_mode = params["add_mode"]
    reduce_mode = params["reduce_mode"]

    n_days = i1 - i0 + 1
    equity = np.empty(n_days, dtype=float)
    pos_series = np.empty(n_days, dtype=float)

    pos = cap  # 期初满仓（上限）
    equity_cur = 1.0
    turnover = 0.0
    scheduled_base_bar = -1  # 分步降仓的第二步（到底仓）bar 索引

    for k in range(n_days):
        t = i0 + k
        # 当天收益（用进入当天的仓位 pos）
        if k > 0:
            prev_close = close[t - 1]
            if prev_close > 0:
                equity_cur *= 1.0 + pos * (close[t] / prev_close - 1.0)
        equity[k] = equity_cur

        prev_pos = pos

        # 分步降仓第二步到期
        if scheduled_base_bar >= 0 and t >= scheduled_base_bar:
            pos = base
            scheduled_base_bar = -1

        if top_div[t]:
            # 顶背离 → 降仓到底仓下限
            if reduce_mode == "once":
                pos = base
                scheduled_base_bar = -1
            else:
                pos = (pos + base) / 2.0  # 确认日降一半
                scheduled_base_bar = t + GRADUAL_STEP_BARS
        elif add_flag[t] and scheduled_base_bar < 0:
            # 单针 → 加仓
            if add_mode == "pp30":
                pos = min(cap, pos + 0.30)
            else:
                pos = min(cap, pos * 1.30)

        turnover += abs(pos - prev_pos)
        pos_series[k] = pos

    ret = equity_cur - 1.0
    mdd = _max_drawdown(equity)
    dr = np.diff(equity) / np.where(equity[:-1] > 0, equity[:-1], 1.0)
    return {
        "total_return": float(ret),
        "max_drawdown": mdd,
        "sharpe": _sharpe(dr),
        "calmar": _calmar(ret, mdd),
        "avg_pos": float(pos_series.mean()),
        "turnover": float(turnover),
    }


def baseline_metrics(close: np.ndarray, i0: int, i1: int, pos_frac: float) -> dict:
    """固定仓位 pos_frac 的基准（买入持有 pos_frac=1.0 / 固定 50% pos_frac=0.5）。

    与状态机同口径：按日复利（equity *= 1 + pos_frac * r_t），而非线性缩放总收益。
    """
    seg = close[i0 : i1 + 1]
    if len(seg) < 2 or seg[0] <= 0:
        return {"total_return": 0.0, "max_drawdown": 0.0, "sharpe": 0.0, "calmar": 0.0,
                "avg_pos": pos_frac, "turnover": 0.0}
    equity = np.empty(len(seg), dtype=float)
    equity[0] = 1.0
    for k in range(1, len(seg)):
        equity[k] = equity[k - 1] * (1.0 + pos_frac * (seg[k] / seg[k - 1] - 1.0))
    ret = float(equity[-1] - 1.0)
    mdd = _max_drawdown(equity)
    dr = np.diff(equity) / equity[:-1]
    return {
        "total_return": ret,
        "max_drawdown": mdd,
        "sharpe": _sharpe(dr),
        "calmar": _calmar(ret, mdd),
        "avg_pos": pos_frac,
        "turnover": 0.0,
    }


METRIC_KEYS = ["total_return", "max_drawdown", "sharpe", "calmar", "avg_pos", "turnover"]


def _agg(rows: list[dict]) -> dict:
    out = {}
    for k in METRIC_KEYS:
        vals = np.asarray([r[k] for r in rows], dtype=float)
        out[k] = {"mean": float(vals.mean()), "median": float(np.median(vals))}
    out["n"] = len(rows)
    return out


def run_window(window: str) -> dict:
    label = WINDOW_LABELS[window]
    start, end = (date.fromisoformat(x) for x in WINDOWS[window])
    from market.calendar import trading_days

    days = trading_days(start, end)
    lookback = len(days) + WARMUP_BARS
    print("\n" + "=" * 80)
    print("【%s】%s ~ %s（%d 交易日，回看 %d 根）" % (label, start, end, len(days), lookback))

    t0 = time.time()
    candles, _kind_map = load_universe(end, lookback, kinds=(SymbolKind.STOCK,), verbose=True)
    print("  加载个股 %d 只，%.1fs，RSS峰值 %.0fMB" % (len(candles), time.time() - t0, peak_rss_mb()))

    start_ord = start.toordinal()
    end_ord = end.toordinal()
    cfg = pin30_default_config()
    min_bars = cfg.min_bars

    # 每个参数组合 + 两个基准，各累积一行指标
    combos = []
    for base in BASES:
        for add_mode in ADD_MODES:
            for cap in CAPS:
                for reduce_mode in REDUCE_MODES:
                    combos.append({"base": base, "add_mode": add_mode, "cap": cap, "reduce_mode": reduce_mode})

    buckets: dict = {"buyhold_100": [], "fixed_50": []}
    for c in combos:
        buckets[_combo_key(c)] = []

    t0 = time.time()
    n_done = 0
    n_total = len(candles)
    for symbol in sorted(candles):
        df = candles[symbol]
        n = len(df)
        if n < min_bars:
            continue
        ordinals = np.array([d.toordinal() for d in df["date"].to_numpy()], dtype=np.int64)
        i0 = int(np.searchsorted(ordinals, start_ord, side="left"))
        i1 = int(np.searchsorted(ordinals, end_ord, side="right")) - 1
        if i1 <= i0:
            continue
        flags = build_flags(df, cfg)
        close = flags["close"]

        # 基准
        buckets["buyhold_100"].append(baseline_metrics(close, i0, i1, 1.0))
        buckets["fixed_50"].append(baseline_metrics(close, i0, i1, 0.5))

        # 状态机
        for c in combos:
            buckets[_combo_key(c)].append(simulate_position(flags, i0, i1, c))

        n_done += 1
        if n_done % 1000 == 0:
            gc.collect()
            print("    ...%d/%d 只，%.1fs，RSS峰值 %.0fMB" % (n_done, n_total, time.time() - t0, peak_rss_mb()), flush=True)

    print("  模拟完成，%d 只，%.1fs" % (n_done, time.time() - t0))

    result: dict = {"window": label, "start": str(start), "end": str(end), "n_stocks": n_done}
    result["baselines"] = {
        "buyhold_100": _agg(buckets["buyhold_100"]),
        "fixed_50": _agg(buckets["fixed_50"]),
    }
    result["default"] = _agg(buckets[_combo_key(DEFAULT_PARAMS)])
    result["default_params"] = DEFAULT_PARAMS
    result["grid"] = {}
    for c in combos:
        result["grid"][_combo_key(c)] = _agg(buckets[_combo_key(c)])

    del candles
    gc.collect()
    return result


def _combo_key(c: dict) -> str:
    return "base%.0f_%s_cap%.0f_%s" % (c["base"] * 100, c["add_mode"], c["cap"] * 100, c["reduce_mode"])


def _fmt_cell(agg: dict, key: str, is_pct: bool) -> str:
    m = agg[key]["mean"]
    if is_pct:
        return "%+.1f%%" % (m * 100)
    return "%.2f" % m


def print_report(results: dict) -> None:
    labels = [l for l in ("IS", "OOS-A", "OOS-B", "OOS-C") if l in results]
    print("\n" + "=" * 112)
    print("pin30 仓位状态机 vs 基准（宇宙均值；收益/回撤/平均仓位为 %，夏普/卡玛为比率）")
    print("=" * 112)
    rows = [
        ("buyhold_100", "买入持有满仓 100%"),
        ("fixed_50", "固定 50% 不动"),
        ("default", "状态机（默认 底仓20% +30pp 上限100% 分步）"),
    ]
    for key, title in rows:
        print("\n  %s" % title)
        hdr = "    %-14s" % "指标"
        for l in labels:
            hdr += "%16s" % l
        print(hdr)
        for mkey, mname, pct in (
            ("total_return", "最终收益", True),
            ("max_drawdown", "最大回撤", True),
            ("sharpe", "夏普", False),
            ("calmar", "卡玛", False),
            ("avg_pos", "平均仓位", True),
            ("turnover", "换手(Σ|Δ|)", False),
        ):
            row = "    %-14s" % mname
            for l in labels:
                if key == "default":
                    agg = results[l]["default"]
                else:
                    agg = results[l]["baselines"][key]
                row += "%16s" % _fmt_cell(agg, mkey, pct)
            print(row)


def main() -> None:
    ap = argparse.ArgumentParser(description="pin30 仓位状态机")
    ap.add_argument("--windows", nargs="+", default=["IS", "A", "B", "C"])
    ap.add_argument("--out", default="data/pin30_state_machine.json")
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
