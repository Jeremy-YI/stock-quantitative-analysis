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

# 行业 → 对应 ETF 的额外关键词（同花顺行业名与 ETF 名不完全一致时用）
ETF_KEYWORD_OVERRIDES = {
    "化学制药": "医药",
    "中药Ⅱ": "中药",
    "光伏设备": "光伏",
    "风电设备": "风电",
    "养殖业": "养殖",
    "农产品加工": "农业",
    "种植业与林业": "农业",
    "贵金属": "黄金",
    "白酒": "酒",
}


def _load_etf_names() -> list[str]:
    """读本地 ETF 名称表，返回名称列表。

    优先用 data/etf_universe.json（scripts/fetch_etf_flow.py 落盘的全市场场内 ETF，
    ~1600 只，覆盖率高）；拿不到才回退到 data/stage17_etf_names.json。
    """
    for rel in ("etf_universe.json", "stage17_etf_names.json"):
        p = ROOT / "data" / rel
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        names = [n for n in data.values() if isinstance(n, str)]
        if names:
            return names
    return []


def _match_etf(sector: str, etf_names: list[str]) -> str | None:
    """按名称找行业对应的 ETF（优先含「xxETF」的、名字最短的）。"""
    kw = ETF_KEYWORD_OVERRIDES.get(sector, sector)
    candidates = [n for n in etf_names if "ETF" in n and kw in n]
    if not candidates:
        return None
    # 优先：名字里出现「kwETF」（紧挨着），其次名字最短
    candidates.sort(key=lambda n: (0 if kw + "ETF" in n else 1, len(n)))
    name = candidates[0]
    i = name.find("ETF")
    return name[: i + 3] if i >= 0 else name


def fetch(days: str) -> dict:
    """抓一个窗口的板块资金流，返回 {top_inflow, top_outflow}。

    注意两个窗口的字段不一样（同花顺接口就这么给）：
      即时：行业-涨跌幅（float）、领涨股、领涨股-涨跌幅
      多日：阶段涨跌幅（字符串带 %），**没有领涨股**
    以前只读「行业-涨跌幅」，所以 3/5/10/20 日窗口的涨跌幅全是 0，看着像没数据。
    """
    import akshare as ak  # 延迟导入，仅本脚本需要

    etf_names = _load_etf_names()
    df = ak.stock_fund_flow_industry(symbol=days)
    rows = []
    for _, r in df.iterrows():
        sector = str(r["行业"])
        # 多日窗口用阶段涨跌幅（字符串带 %），即时窗口用行业-涨跌幅
        change = r.get("行业-涨跌幅")
        if change is None or (isinstance(change, float) and change != change):
            change = r.get("阶段涨跌幅")
        rows.append({
            "sector": sector,
            "etf": _match_etf(sector, etf_names),
            "change_pct": _f(change),
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
    """安全转 float：兼容 '12.24%' 这种带百分号的字符串。"""
    try:
        if v is None or (isinstance(v, float) and v != v):
            return 0.0
        if isinstance(v, str):
            v = v.strip().replace("%", "").replace(",", "")
            if not v or v in {"-", "--"}:
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
