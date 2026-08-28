#!/usr/bin/env python3
"""阈值敏感性分析：对 b1b2b3 / pin30 的关键阈值做单变量扫描，
看「超额胜率」和「日均信号数」随阈值收紧怎么变。

目的（阶段 4.5，见 docs/阈值敏感性分析.md）：

    - b1b2b3 日均 3160 条信号、选择性 57%，几乎等于全市场随机触发，没有筛选作用；
    - pin30 也偏宽（日均 1620 条）。
    本脚本把关键阈值逐步收紧（如 J<16 → J<10、PCT≥3.7 → ≥5），观察
    「超额胜率」是否上升、「信号数」是否降到仍有统计意义（日均 ≥5 条）的区间。

重要：本脚本只做敏感性分析、只输出建议，**不改各策略 config.py 的默认值**——
那是 Jeremy 的交易框架，是否调整由他自己决定。

数据源：本地 hsjday（只读）。默认区间 2026-03-01 ~ 2026-08-27（与回测一致）。

性能：预计算每只标的的指标序列（KDJ / 量比 / EMA / 随机位置），阈值扫描只是
numpy 布尔过滤 + 前向收益聚合，单策略全量扫描约几十秒，不重复算指标。

用法（仓库根目录）：

    .venv/bin/python scripts/threshold_sensitivity.py [--start 2026-03-01 --end 2026-08-27]
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from indicators.kdj import calc_kdj
from indicators.macd import calc_ema
from indicators.volume import calc_volume_ratio
from datasource.tdx import resolve_hsjday_root
from strategies.filters import SymbolKind, filter_for_kinds
from strategies.scanner import MarketScanner
from market.calendar import trading_days

# 数据根目录：优先读环境变量 STOCK_HSJDAY_ROOT，缺省用本地默认路径
HSJDAY = resolve_hsjday_root()
HOLD_DAYS = (1, 3, 5, 10, 20)

# 各策略默认阈值（与 config.py 一致，仅用于标注 baseline 与扫描基准）
B1B2B3_DEFAULT = dict(
    j_b1=16.0, k_b1=30.0, pct_b2=3.7, vr_b2=1.2, vr_b3=0.8, range_b3=8.0, min_bars=10,
)
PIN30_DEFAULT = dict(
    short_threshold=30.0, long_threshold=80.0, j_b1w=16.0,
    short_lookback=3, long_lookback=20, st_period=10,
    lt_periods=(14, 28, 57, 114), min_bars=120,
)


def _sma_series(closes: np.ndarray, period: int) -> np.ndarray:
    """SMA 序列（窗口不足用已有数据平均，与策略 _sma 一致）。"""
    cs = np.cumsum(closes)
    n = len(closes)
    out = np.empty(n)
    for i in range(n):
        if i >= period:
            out[i] = (cs[i] - cs[i - period]) / period
        elif i == period - 1:
            out[i] = cs[i] / period
        else:
            out[i] = cs[i] / (i + 1)
    return out


def _stochastic_series(closes: np.ndarray, lows: np.ndarray, lookback: int) -> np.ndarray:
    """随机位置序列 (C-LLV(L,n))/(HHV(C,n)-LLV(L,n))*100，与策略 _stochastic 一致。"""
    n = len(closes)
    out = np.empty(n)
    for i in range(n):
        s = max(0, i - lookback + 1)
        lv = lows[s : i + 1].min()
        hv = closes[s : i + 1].max()
        den = hv - lv
        out[i] = 50.0 if den <= 0 else (closes[i] - lv) / (den + 0.0001) * 100.0
    return out


def _precompute_b1b2b3(df) -> dict | None:
    """预计算 b1b2b3 所需的日级指标数组。"""
    n = len(df)
    if n < B1B2B3_DEFAULT["min_bars"]:
        return None
    close = df["close"].astype(float).to_numpy()
    high = df["high"].astype(float).to_numpy()
    low = df["low"].astype(float).to_numpy()
    volume = df["volume"].astype(float).to_numpy()
    dates = df["date"].to_numpy()

    k, d, j = calc_kdj(high.tolist(), low.tolist(), close.tolist())
    vr = calc_volume_ratio(volume.tolist())
    j = np.asarray(j, dtype=float)
    k = np.asarray(k, dtype=float)
    vr = np.asarray(vr, dtype=float)

    # pct（当日涨幅 %）
    close_prev = np.empty(n)
    close_prev[0] = close[0]
    close_prev[1:] = close[:-1]
    pct = np.where(close_prev > 0, (close - close_prev) / close_prev * 100.0, 0.0)

    # 5 日振幅 %
    range_5d = np.empty(n)
    for i in range(n):
        s = max(0, i - 4)
        rng = high[s : i + 1].max() - low[s : i + 1].min()
        range_5d[i] = rng / close[i] * 100.0 if close[i] else 0.0

    is_yang = close > close_prev
    j_prev = np.empty(n)
    j_prev[0] = j[0]
    j_prev[1:] = j[:-1]
    j_up = j > j_prev

    return dict(
        dates=dates, close=close, j=j, k=k, vr=vr, pct=pct,
        range_5d=range_5d, is_yang=is_yang, j_up=j_up, min_bars=B1B2B3_DEFAULT["min_bars"],
    )


def _precompute_pin30(df) -> dict | None:
    """预计算 pin30 所需的日级指标数组。"""
    n = len(df)
    if n < PIN30_DEFAULT["min_bars"]:
        return None
    close = df["close"].astype(float).to_numpy()
    high = df["high"].astype(float).to_numpy()
    low = df["low"].astype(float).to_numpy()

    st = PIN30_DEFAULT["st_period"]
    st_raw = np.asarray(calc_ema(calc_ema(close.tolist(), st), st), dtype=float)
    lt_periods = PIN30_DEFAULT["lt_periods"]
    lt_raw = np.mean(
        np.stack([_sma_series(close, p) for p in lt_periods]), axis=0
    )
    trend_long = (st_raw > lt_raw) & (close > lt_raw)

    short_val = _stochastic_series(close, low, PIN30_DEFAULT["short_lookback"])
    long_val = _stochastic_series(close, low, PIN30_DEFAULT["long_lookback"])

    _k, _d, j = calc_kdj(high.tolist(), low.tolist(), close.tolist())
    j = np.asarray(j, dtype=float)

    return dict(
        dates=df["date"].to_numpy(), close=close, trend_long=trend_long,
        short_val=short_val, long_val=long_val, j=j,
        min_bars=PIN30_DEFAULT["min_bars"],
    )


def _eligible_idx(dates: np.ndarray, start: date, end: date, min_bars: int) -> np.ndarray:
    """返回区间内、且历史足够（index >= min_bars-1）的日级索引。"""
    n = len(dates)
    mask = (dates >= start) & (dates <= end) & (np.arange(n) >= min_bars - 1)
    return np.nonzero(mask)[0]


def _eval_b1b2b3(store: list, start: date, end: date, cfg: dict, baseline: dict):
    """扫描 b1b2b3，返回 (总信号, 日均信号, 各持有期胜率, 各持有期超额胜率, 各持有期样本)。"""
    hold_days = list(baseline.keys())
    total = 0
    wins = {h: 0 for h in hold_days}
    samples = {h: 0 for h in hold_days}
    for s in store:
        dates = s["dates"]
        n = len(s["close"])
        idx = _eligible_idx(dates, start, end, s["min_bars"])
        if idx.size == 0:
            continue
        b1 = (s["j"][idx] < cfg["j_b1"]) | (s["k"][idx] <= cfg["k_b1"])
        b2 = (
            (s["pct"][idx] >= cfg["pct_b2"])
            & s["is_yang"][idx]
            & (s["vr"][idx] > cfg["vr_b2"])
            & s["j_up"][idx]
        )
        b3 = (s["vr"][idx] < cfg["vr_b3"]) & (s["range_5d"][idx] < cfg["range_b3"])
        trig = b1.astype(int) + b2.astype(int) + b3.astype(int)
        total += int(trig.sum())
        close = s["close"]
        for h in hold_days:
            jj = idx + h
            valid = jj < n
            if not valid.any():
                continue
            fr = close[jj[valid]] / close[idx[valid]] - 1.0
            pos = (fr > 0).astype(int)
            w = trig[valid]
            wins[h] += int((pos * w).sum())
            samples[h] += int(w.sum())

    n_days = len(trading_days(start, end))
    win_rate = {h: wins[h] / samples[h] if samples[h] else 0.0 for h in hold_days}
    excess = {h: win_rate[h] - baseline[h]["win_rate"] for h in hold_days}
    return total, total / n_days if n_days else 0.0, win_rate, excess, samples


def _eval_pin30(store: list, start: date, end: date, cfg: dict, baseline: dict):
    """扫描 pin30，返回与 _eval_b1b2b3 相同结构的统计。"""
    hold_days = list(baseline.keys())
    total = 0
    wins = {h: 0 for h in hold_days}
    samples = {h: 0 for h in hold_days}
    for s in store:
        dates = s["dates"]
        n = len(s["close"])
        idx = _eligible_idx(dates, start, end, s["min_bars"])
        if idx.size == 0:
            continue
        pin30 = (
            s["trend_long"][idx]
            & (s["short_val"][idx] <= cfg["short_threshold"])
            & (s["long_val"][idx] >= cfg["long_threshold"])
        )
        b1_w = s["j"][idx] < cfg["j_b1w"]
        trig = pin30.astype(int) + b1_w.astype(int)
        total += int(trig.sum())
        close = s["close"]
        for h in hold_days:
            jj = idx + h
            valid = jj < n
            if not valid.any():
                continue
            fr = close[jj[valid]] / close[idx[valid]] - 1.0
            pos = (fr > 0).astype(int)
            w = trig[valid]
            wins[h] += int((pos * w).sum())
            samples[h] += int(w.sum())

    n_days = len(trading_days(start, end))
    win_rate = {h: wins[h] / samples[h] if samples[h] else 0.0 for h in hold_days}
    excess = {h: win_rate[h] - baseline[h]["win_rate"] for h in hold_days}
    return total, total / n_days if n_days else 0.0, win_rate, excess, samples


def _fmt_row(tag, total, spd, win_rate, excess, samples, baseline):
    cells = []
    for h in HOLD_DAYS:
        ex = excess.get(h)
        cells.append(
            f"{win_rate.get(h, 0)*100:5.1f}%/{ex*100:+5.1f}pp"
        )
    return (
        f"  {tag:<22s} 信号{total:>7d}  日均{spd:>7.1f}  "
        + "  ".join(cells)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="阈值敏感性分析")
    parser.add_argument("--start", default="2026-03-01")
    parser.add_argument("--end", default="2026-08-27")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    t0 = time.time()
    print(f"加载个股 K 线（尾段 800）...", flush=True)
    scanner = MarketScanner(HSJDAY)
    candles = scanner.load_candles(end, filter_config=filter_for_kinds((SymbolKind.STOCK,)))
    print(f"  已加载 {len(candles)} 只个股，耗时 {time.time()-t0:.1f}s", flush=True)

    # 预计算两套指标
    print("预计算指标（KDJ/量比/EMA/随机位置）...", flush=True)
    b1_store, pin_store = [], []
    for symbol, df in candles.items():
        s1 = _precompute_b1b2b3(df)
        if s1:
            b1_store.append(s1)
        s2 = _precompute_pin30(df)
        if s2:
            pin_store.append(s2)
    print(
        f"  b1b2b3 标的 {len(b1_store)}，pin30 标的 {len(pin_store)}，"
        f"耗时 {time.time()-t0:.1f}s",
        flush=True,
    )

    # 基线（个股宇宙，同期）
    from backtest.baseline import compute_baseline
    base_stats = compute_baseline(
        candles, set(candles.keys()), "stock", start, end, list(HOLD_DAYS)
    )
    baseline = {h.hold_days: {"win_rate": h.win_rate, "avg_return": h.avg_return} for h in base_stats.holds}
    print("\n同期个股基线（正收益比例 / 平均收益）：")
    for h in base_stats.holds:
        print(f"  持有 {h.hold_days:>2d} 日  {h.win_rate*100:5.1f}%  {h.avg_return*100:+6.2f}%")

    print(f"\n{'='*100}")
    print("【b1b2b3】阈值敏感性（列 = 持有日「胜率/超额胜率」）")
    print(f"{'='*100}")
    b1_sweeps = [
        ("默认 J<16/PCT≥3.7", dict(B1B2B3_DEFAULT)),
        ("J<12", {**B1B2B3_DEFAULT, "j_b1": 12.0}),
        ("J<10", {**B1B2B3_DEFAULT, "j_b1": 10.0}),
        ("J<8", {**B1B2B3_DEFAULT, "j_b1": 8.0}),
        ("K≤25", {**B1B2B3_DEFAULT, "k_b1": 25.0}),
        ("K≤20", {**B1B2B3_DEFAULT, "k_b1": 20.0}),
        ("PCT≥5.0", {**B1B2B3_DEFAULT, "pct_b2": 5.0}),
        ("PCT≥6.0", {**B1B2B3_DEFAULT, "pct_b2": 6.0}),
        ("J<10+PCT≥5.0", {**B1B2B3_DEFAULT, "j_b1": 10.0, "pct_b2": 5.0}),
        ("J<8+PCT≥5.0", {**B1B2B3_DEFAULT, "j_b1": 8.0, "pct_b2": 5.0}),
    ]
    for tag, cfg in b1_sweeps:
        total, spd, wr, excess, samples = _eval_b1b2b3(b1_store, start, end, cfg, baseline)
        print(_fmt_row(tag, total, spd, wr, excess, samples, baseline))

    print(f"\n{'='*100}")
    print("【pin30】阈值敏感性（列 = 持有日「胜率/超额胜率」）")
    print(f"{'='*100}")
    pin_sweeps = [
        ("默认 短期≤30/J<16", dict(PIN30_DEFAULT)),
        ("短期≤25", {**PIN30_DEFAULT, "short_threshold": 25.0}),
        ("短期≤20", {**PIN30_DEFAULT, "short_threshold": 20.0}),
        ("短期≤15", {**PIN30_DEFAULT, "short_threshold": 15.0}),
        ("J<12", {**PIN30_DEFAULT, "j_b1w": 12.0}),
        ("J<10", {**PIN30_DEFAULT, "j_b1w": 10.0}),
        ("J<8", {**PIN30_DEFAULT, "j_b1w": 8.0}),
        ("短期≤20+J<10", {**PIN30_DEFAULT, "short_threshold": 20.0, "j_b1w": 10.0}),
        ("短期≤15+J<10", {**PIN30_DEFAULT, "short_threshold": 15.0, "j_b1w": 10.0}),
    ]
    for tag, cfg in pin_sweeps:
        total, spd, wr, excess, samples = _eval_pin30(pin_store, start, end, cfg, baseline)
        print(_fmt_row(tag, total, spd, wr, excess, samples, baseline))

    print(f"\n总耗时 {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
