#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OAMV 拟合引擎（RAG 迭代的核心计算层）。

目标：无限逼近指南针「活跃市值(OAMV)」真实值。
代理假设：OAMV ≈ Σ(流通股本 × 前复权收盘 × (收盘 > MA_N))，扫描多个 N 找最优。

与废弃的「K×EMA(成交额)」不同，这里用的是「流通市值 × 站上均线」，
口径与真实活跃市值（站上成本线的流通市值）一致，方向不再受缩量上涨干扰。

运行（stock-quant 根目录，venv）：
    .venv/bin/python scripts/oamv_rag_fit.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datasource.tdx.reader import resolve_hsjday_root, resolve_symbol_path, parse_day_file
from market.adjust import forward_adjust_frame
from scripts.run_stage16 import list_stock_symbols

MEM = Path.home() / ".openclaw/workspace/memory/oamv_series.json"
MA_WINDOWS = [3, 5, 8, 10, 13, 20, 34, 60, 120, 250]


def load_ground_truth() -> pd.DataFrame:
    d = json.loads(MEM.read_text(encoding="utf-8"))
    rows = [e for e in d["series"] if str(e.get("source", "")).startswith("截图OCR")]
    gt = pd.DataFrame(rows)
    gt["date"] = pd.to_datetime(gt["date"]).dt.date
    return gt.sort_values("date").reset_index(drop=True)


def load_float_shares() -> dict:
    mcap = json.loads((ROOT / "data" / "stage18_float_mcap.json").read_text(encoding="utf-8"))
    return {
        c: v["float_mcap"] * 1e8 / v["price"]
        for c, v in mcap.items()
        if v.get("price", 0) > 0 and v.get("float_mcap", 0) > 0
    }


def load_stock_closes(weights: dict, root: Path) -> dict:
    symbols = list_stock_symbols(root, "hs")
    data: dict = {}
    for code in symbols:
        if code not in weights:
            continue
        try:
            df = parse_day_file(resolve_symbol_path(root, code))
        except FileNotFoundError:
            continue
        if len(df) < 255:
            continue
        df = forward_adjust_frame(df, code)
        data[code] = (df["date"].to_numpy(), df["close"].astype(float).to_numpy())
    return data


def build_proxy(data: dict, weights: dict, window: int) -> pd.Series:
    acc: dict = {}
    for code, (dates, close) in data.items():
        ma = pd.Series(close).rolling(window, min_periods=window).mean().to_numpy()
        active = close > ma
        val = weights[code] * close * active
        for d, v in zip(dates, val):
            if v > 0:
                acc[d] = acc.get(d, 0.0) + v
    return pd.Series({d: acc[d] / 1e8 for d in sorted(acc)})


def main() -> None:
    gt = load_ground_truth()
    weights = load_float_shares()
    root = resolve_hsjday_root()
    data = load_stock_closes(weights, root)
    latest = max(d[0][-1] for d in data.values()) if data else None
    print(f"个股 {len(data)} 只 | 真实样本 {len(gt)} 个 | hsjday 最新交易日 {latest}\n")

    results = []
    for w in MA_WINDOWS:
        proxy = build_proxy(data, weights, w)
        est, real = [], []
        for _, r in gt.iterrows():
            d = r["date"]
            idx = proxy.index[proxy.index <= d]
            est.append(proxy.loc[idx[-1]] if len(idx) else np.nan)
            real.append(float(r["value"]))
        est, real = np.array(est, float), np.array(real, float)
        mask = np.isfinite(est)
        if mask.sum() < 2:
            continue
        rel_err = float(np.mean(np.abs(est[mask] - real[mask]) / real[mask]) * 100)
        a, b = np.polyfit(est[mask], real[mask], 1)
        fitted = a * est[mask] + b
        rel_err_affine = float(np.mean(np.abs(fitted - real[mask]) / real[mask]) * 100)
        dir_hit = dir_tot = 0
        for i in range(1, len(real)):
            if not (np.isfinite(est[i - 1]) and np.isfinite(est[i])):
                continue
            dr, de = np.sign(real[i] - real[i - 1]), np.sign(est[i] - est[i - 1])
            if dr == 0 or de == 0:
                continue
            dir_tot += 1
            dir_hit += int(dr == de)
        results.append(dict(
            window=w, rel_err=rel_err, rel_err_affine=rel_err_affine,
            scale_a=float(a), offset_b=float(b), dir_hit=dir_hit, dir_tot=dir_tot,
        ))

    results.sort(key=lambda x: (-x["dir_hit"], x["rel_err_affine"]))
    print(f"{'窗口':>5} | {'原始误差%':>9} | {'仿射误差%':>9} | {'缩放a':>8} | {'截距b':>9} | {'方向命中':>7}")
    for r in results:
        print(f"{r['window']:>5} | {r['rel_err']:>9.2f} | {r['rel_err_affine']:>9.2f} "
              f"| {r['scale_a']:>8.3f} | {r['offset_b']:>9.0f} | {r['dir_hit']:>3}/{r['dir_tot']}")

    best = results[0]
    w = best["window"]
    proxy = build_proxy(data, weights, w)
    print(f"\n=== 最佳窗口 MA{w} 每日明细 ===")
    print(f"{'日期':>12} | {'代理(亿)':>12} | {'真实(亿)':>12} | {'代理%':>8} | {'真实%':>8}")
    pe = pr = None
    for _, r in gt.iterrows():
        d = r["date"]
        idx = proxy.index[proxy.index <= d]
        e = proxy.loc[idx[-1]] if len(idx) else np.nan
        rv = float(r["value"])
        pe_s = "" if pe is None else f"{(e / pe - 1) * 100:+.2f}"
        pr_s = "" if pr is None else f"{(rv / pr - 1) * 100:+.2f}"
        print(f"{r['date']} | {e:>12,.0f} | {rv:>12,.0f} | {pe_s:>8} | {pr_s:>8}")
        pe, pr = e, rv


if __name__ == "__main__":
    main()
