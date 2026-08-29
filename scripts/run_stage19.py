#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 19：上证指数顶/底背离触发器 + regime 切换回测（首版）。

Jeremy 2026-08-30 口述的策略：
  - 衰竭型双顶 / 顶背离（上证指数）→ 清仓科技 → 切红利（国家队/资金进红利就跟进）
  - 双底 / 底背离（上证指数）→ 切「资金流入板块」个股（如 2025/26 半导体）
  - 例：2026-06-23 顶背离 → 此后只买红利；2026-08-03 双底 → 买资金流入板块

首版口径（可后续加严）：
  - 触发器：上证指数日线 MACD(12,26,9)。顶背离 = 衰竭型（次高允许比前高低 2%、
    DIF 跌幅 >=30%，阶段12 divergence 模块）；底背离 = 双底齐平/略高 + DIF/柱/RSI 抬升。
  - 篮子 A（成长/资金流入） = 半导体板块成分（sector_stocks.json），等权。
  - 篮子 B（红利） = 中证红利 000922 成分，等权。
  - 切换：背离「确认日」收盘生效（无前视；确认日 = 右侧 pivot + k 根）。
  - 对照：一直持半导体 / 一直持红利 / 上证指数。

价量代理说明：历史主力资金流本地没有，本版用「半导体」当成长/资金流入板块的代理
（Jeremy 2025/26 明确点名的板块）；后续可换成「20 日相对强度最强的板块」动态选。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datasource.tdx.reader import resolve_hsjday_root, resolve_symbol_path, parse_day_file
from market.adjust import forward_adjust_frame
from indicators.divergence.divergence import detect_bearish_divergences, detect_bullish_divergences

PERIOD_START = date(2020, 1, 1)
PERIOD_END = date(2026, 8, 28)
K = 6
TOP_TOL_LOWER = 0.02     # 衰竭型：次高允许比前高低 2%
DIF_DROP = 0.30          # DIF 跌幅阈值


def ema(s: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(s).ewm(span=n, adjust=False).mean().to_numpy()


def rsi14(c: np.ndarray) -> np.ndarray:
    d = pd.Series(c).diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    rs = up / dn
    return (100 - 100 / (1 + rs)).to_numpy()


def basket_daily_returns(codes: list[str], root: Path) -> pd.Series:
    """等权日收益序列（前复权），按日期索引。"""
    acc: dict[date, list[float]] = {}
    for code in codes:
        try:
            df = parse_day_file(resolve_symbol_path(root, code))
        except FileNotFoundError:
            continue
        if len(df) < 60:
            continue
        df = forward_adjust_frame(df, code)
        c = df["close"].astype(float).to_numpy()
        r = np.diff(c) / c[:-1]
        for d, rr in zip(df["date"].to_numpy()[1:], r):
            acc.setdefault(d, []).append(rr)
    idx = sorted(acc)
    mean = [float(np.mean(acc[d])) for d in idx]
    return pd.Series(mean, index=idx)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/stage19_results.json")
    args = ap.parse_args()

    root = resolve_hsjday_root()

    # 上证指数 + 背离
    df = parse_day_file(root / "sh" / "lday" / "sh000001.day")
    c = df["close"].astype(float).to_numpy()
    h = df["high"].astype(float).to_numpy()
    l = df["low"].astype(float).to_numpy()
    dates = df["date"].to_numpy()
    dif = ema(c, 12) - ema(c, 26)
    dea = ema(dif, 9)
    hist = (dif - dea) * 2
    rsi = rsi14(c)

    top = detect_bearish_divergences(list(h), list(dif), list(hist), k=K,
                                     tol_lower=TOP_TOL_LOWER, min_dif_drop_ratio=DIF_DROP)
    bot = detect_bullish_divergences(list(l), list(dif), list(hist), list(rsi), k=K)

    # 篮子
    idx = json.loads((ROOT / "data" / "stage18_index_universes.json").read_text())
    div_codes = sorted(idx["000922"]["stocks"])
    sec = json.loads(Path("/Users/yanhongyi/Documents/Obsidian Vault/大富翁/A股/A持仓-复盘/A每日复盘/板块资金流向/sector_stocks.json").read_text())
    semi_codes = sorted(sec["半导体"]["stocks"])

    div_r = basket_daily_returns(div_codes, root)
    semi_r = basket_daily_returns(semi_codes, root)

    # 交易日历（上证指数，2020 起）
    idx_sel = [i for i, d in enumerate(dates) if PERIOD_START <= d <= PERIOD_END]
    cal_dates = [dates[i] for i in idx_sel]
    n = len(cal_dates)

    # 上证指数日收益（同日历）
    mkt_ret = np.zeros(n)
    for j in range(1, n):
        mkt_ret[j] = c[idx_sel[j]] / c[idx_sel[j] - 1] - 1.0

    # 篮子日收益对齐到日历
    def align(s: pd.Series) -> np.ndarray:
        out = np.zeros(n)
        prev = None
        for j, d in enumerate(cal_dates):
            if d in s.index:
                out[j] = float(s.loc[d])
            else:
                out[j] = 0.0
        return out

    div_ret = align(div_r)
    semi_ret = align(semi_r)

    # regime 时间线：初始 = 成长（risk_on），背离确认日收盘切换到新 regime
    # 确认日 = confirmed_bar 索引（在完整序列上），需映射到日历
    events = []
    for d in top:
        events.append((d.confirmed_bar, "top"))
    for d in bot:
        events.append((d.confirmed_bar, "bottom"))
    events.sort()

    # 完整序列索引 -> 日历索引
    full_to_cal = {i: j for j, i in enumerate(idx_sel)}

    regime = np.ones(n, dtype=bool)  # True = risk_on（半导体）
    for fi, kind in events:
        if kind == "top":
            state = False
        else:
            state = True
        # 生效：确认日之后（收盘生效，次日持有）
        cj = full_to_cal.get(fi, None)
        if cj is None or cj + 1 >= n:
            continue
        regime[cj + 1:] = state

    # 策略日收益
    strat_ret = np.where(regime, semi_ret, div_ret)

    # 累积收益
    def cum(r):
        return float(np.prod(1.0 + r) - 1.0)

    out = {
        "meta": {"period": [str(PERIOD_START), str(PERIOD_END)],
                 "n_top_div": len(top), "n_bot_div": len(bot),
                 "k": K, "top_tol_lower": TOP_TOL_LOWER, "dif_drop": DIF_DROP},
        "events": [{"idx": fi, "kind": kd, "date": str(dates[fi])} for fi, kd in events
                   if PERIOD_START <= dates[fi] <= PERIOD_END],
        "cumulative": {
            "strategy_switch": cum(strat_ret),
            "always_semi": cum(semi_ret),
            "always_div": cum(div_ret),
            "sh_index": cum(mkt_ret),
        },
        "annualized": {
            "strategy_switch": float((1 + cum(strat_ret)) ** (252.0 / n) - 1),
            "always_semi": float((1 + cum(semi_ret)) ** (252.0 / n) - 1),
            "always_div": float((1 + cum(div_ret)) ** (252.0 / n) - 1),
            "sh_index": float((1 + cum(mkt_ret)) ** (252.0 / n) - 1),
        },
        "sharpe": {
            "strategy_switch": float(np.mean(strat_ret) / (np.std(strat_ret) + 1e-12) * np.sqrt(252)),
            "always_semi": float(np.mean(semi_ret) / (np.std(semi_ret) + 1e-12) * np.sqrt(252)),
            "always_div": float(np.mean(div_ret) / (np.std(div_ret) + 1e-12) * np.sqrt(252)),
        },
        "max_drawdown": {
            "strategy_switch": float(np.min(np.cumprod(1 + strat_ret) / np.maximum.accumulate(np.cumprod(1 + strat_ret)) - 1)),
            "always_semi": float(np.min(np.cumprod(1 + semi_ret) / np.maximum.accumulate(np.cumprod(1 + semi_ret)) - 1)),
            "always_div": float(np.min(np.cumprod(1 + div_ret) / np.maximum.accumulate(np.cumprod(1 + div_ret)) - 1)),
        },
        "time_in_semi": float(np.mean(regime)),
    }

    (ROOT / args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print("顶背离 %d 次，底背离 %d 次" % (len(top), len(bot)))
    print("切换事件（2020 起）：")
    for e in out["events"]:
        print("   %s  %s" % (e["date"], "顶→红利" if e["kind"] == "top" else "底→半导体"))
    print("\n累积收益（2020-01 ~ 2026-08）：")
    for k, v in out["cumulative"].items():
        print("   %-18s %+8.2f%%" % (k, v * 100))
    print("\n年化：")
    for k, v in out["annualized"].items():
        print("   %-18s %+8.2f%%" % (k, v * 100))
    print("\n最大回撤：")
    for k, v in out["max_drawdown"].items():
        print("   %-18s %+8.2f%%" % (k, v * 100))
    print("\n时间在半导体（risk_on）占比 %.0f%%" % (out["time_in_semi"] * 100))


if __name__ == "__main__":
    main()
