#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""活跃市值代理每日监测（告警用）。

活跃市值(OAMV) 数据无法程序化获取（指南针 WebSocket 推送），用「全市场流通市值 × 站上MA250」
代理近似。代理波动约为真实活跃市值的 3~5 倍，阈值按比例放大（粗筛，仅供提醒 Jeremy 去确认）。

输出：若无信号打印 NO_SIGNAL；有信号打印一句话告警（供 cron 投递到飞书）。
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datasource.tdx.reader import resolve_hsjday_root, resolve_symbol_path, parse_day_file
from market.adjust import forward_adjust_frame
from scripts.run_stage16 import list_stock_symbols

# 阈值（代理口径，约为活跃市值 -2.3%/+4% 的 3~5 倍，粗筛用）
BUY_THRESHOLD = 0.05    # 代理单日涨 >5% ≈ 活跃市值 +4%
SELL_THRESHOLD = -0.05  # 代理单日跌 < -5% ≈ 活跃市值 -2.3%
MA_WINDOW = 250


def main() -> None:
    root = resolve_hsjday_root()
    mcap = json.loads((ROOT / "data" / "stage18_float_mcap.json").read_text())
    weights = {c: v["float_mcap"] * 1e8 / v["price"]
               for c, v in mcap.items() if v.get("price", 0) > 0 and v.get("float_mcap", 0) > 0}

    symbols = list_stock_symbols(root, "hs")
    acc = {}
    for code in symbols:
        if code not in weights:
            continue
        try:
            df = parse_day_file(resolve_symbol_path(root, code))
        except FileNotFoundError:
            continue
        if len(df) < MA_WINDOW + 5:
            continue
        df = forward_adjust_frame(df, code)
        c = df["close"].astype(float).to_numpy()
        ma = pd.Series(c).rolling(MA_WINDOW, min_periods=MA_WINDOW).mean().to_numpy()
        active = c > ma
        val = weights[code] * c * active
        for d, v in zip(df["date"], val):
            if v > 0:
                acc[d] = acc.get(d, 0.0) + v

    s = pd.Series({d: acc[d] for d in sorted(acc)})
    r = s.pct_change().dropna()
    if len(r) < 3:
        print("NO_SIGNAL")
        return

    last_date = r.index[-1]
    last3 = r.iloc[-3:]
    latest = float(last3.iloc[-1])

    # 判断
    signal = None
    if latest >= BUY_THRESHOLD:
        signal = "买入信号（活跃市值代理单日 +%.1f%%，可能对应活跃市值 +4%）" % (latest * 100)
    elif latest <= SELL_THRESHOLD:
        signal = "卖出信号（活跃市值代理单日 %.1f%%，可能对应活跃市值 -2.3%）" % (latest * 100)

    if signal:
        print("【活跃市值代理告警】%s（%s）\n近3日代理涨跌：%s。请到指南针确认活跃市值是否真出信号。" % (
            signal, last_date,
            " / ".join("%+.1f%%" % (x * 100) for x in last3)))
    else:
        print("NO_SIGNAL")


if __name__ == "__main__":
    main()
