#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取同花顺行业资金流，落盘成 JSON 快照（供 API 读取）。

API 的 venv 不装 akshare（避免重依赖），本脚本用系统 python3 跑（有 akshare），
每天收盘后由 cron 调用一次，产出 data/sector_flow.json：
{"即时": {...}, "3日排行": {...}, ...}，每个窗口含 top_inflow / top_outflow。

用法：python3 scripts/fetch_sector_flow.py [--out data/sector_flow.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DAYS = ["即时", "3日排行", "5日排行", "10日排行", "20日排行"]


def fetch(days: str) -> dict:
    """抓一个窗口的板块资金流，返回 {top_inflow, top_outflow}。"""
    import akshare as ak  # 延迟导入，仅本脚本需要

    df = ak.stock_fund_flow_industry(symbol=days)
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "sector": str(r["行业"]),
            "change_pct": _f(r.get("行业-涨跌幅")),
            "inflow": _f(r.get("流入资金")),
            "outflow": _f(r.get("流出资金")),
            "net": _f(r.get("净额")),
            "companies": _i(r.get("公司家数")),
            "leader": str(r.get("领涨股") or ""),
            "leader_pct": _f(r.get("领涨股-涨跌幅")),
        })
    by_net = sorted(rows, key=lambda x: x["net"], reverse=True)
    return {
        "top_inflow": [x for x in by_net if x["net"] > 0][:20],
        "top_outflow": sorted([x for x in by_net if x["net"] < 0], key=lambda x: x["net"])[:20],
    }


def _f(v) -> float:
    try:
        if v is None or (isinstance(v, float) and v != v):
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _i(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "sector_flow.json"))
    args = ap.parse_args()

    result = {}
    for d in DAYS:
        try:
            result[d] = fetch(d)
            print("抓取", d, "OK")
        except Exception as e:
            print("抓取", d, "失败:", str(e)[:120], file=sys.stderr)

    out = Path(args.out)
    out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print("落盘", out)


if __name__ == "__main__":
    main()
