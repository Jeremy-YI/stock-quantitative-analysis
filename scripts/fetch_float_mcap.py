#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拉取全 A 股流通市值/总市值（腾讯行情接口，含流通市值字段）。

东财 82.push2 被断、新浪无市值字段，腾讯 qt.gtimg.cn 有流通市值(字段44)/总市值(字段45)。
输出 data/stage18_float_mcap.json = {code: {"name":..., "float_mcap":亿元, "total_mcap":亿元, "price":元}}
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_stage16 import list_stock_symbols
from datasource.tdx.reader import resolve_hsjday_root

H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
     "Referer": "http://finance.qq.com/"}


def tx_symbol(code: str) -> str:
    if code.startswith(("60", "68", "9")):
        return "sh" + code
    return "sz" + code


def fetch_batch(codes: list[str]) -> dict[str, dict]:
    syms = [tx_symbol(c) for c in codes]
    url = "http://qt.gtimg.cn/q=" + ",".join(syms)
    out = {}
    r = requests.get(url, headers=H, timeout=20)
    for line in r.text.split(";"):
        if "=" not in line or "v_" not in line:
            continue
        code = line.split("=")[0].replace("v_", "")[2:]
        f = line.split('"')[1].split("~")
        if len(f) <= 45:
            continue
        try:
            out[code] = {"name": f[1], "price": float(f[3]),
                         "float_mcap": float(f[44]), "total_mcap": float(f[45])}
        except (ValueError, IndexError):
            continue
    return out


def main() -> None:
    root = resolve_hsjday_root()
    symbols = list_stock_symbols(root, "hs")
    print("全市场 hs 个股 %d 只" % len(symbols))

    result = {}
    B = 60
    for i in range(0, len(symbols), B):
        batch = symbols[i:i + B]
        for attempt in range(3):
            try:
                result.update(fetch_batch(batch))
                break
            except Exception:
                time.sleep(1.0)
        if (i // B) % 20 == 0:
            print("  %d/%d，成功 %d" % (i, len(symbols), len(result)), flush=True)
        time.sleep(0.15)

    (ROOT / "data" / "stage18_float_mcap.json").write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print("落盘 %d 只" % len(result))


if __name__ == "__main__":
    main()
