#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓 A股代码 → 名称映射，落盘 data/stock_names.json（供 API 展示名称 + 过滤 ST）。

为什么要单独一份：
  1. 推荐列表只给 6 位代码，客户看不懂，必须显示名称
  2. **ST / *ST / 退市整理期不能推荐给客户**，靠名称前缀判定最省事也最准
     （交易所对风险警示股票的标识就在证券简称上）

数据源：优先交易所官网（深交所/上交所/北交所名称表，权威且不跟东财限流抢资源），
全失败时回退 stock_zh_a_spot_em()。

输出格式：
{
  "as_of": "2026-08-31",
  "count": 5400,
  "stocks": { "600519": {"name": "贵州茅台", "st": false}, ... }
}

用法：python3 scripts/fetch_stock_names.py [--out data/stock_names.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 风险警示 / 退市标识：出现在证券简称里就不推荐
ST_MARKERS = ("ST", "*ST", "退", "退市")


def is_st_name(name: str) -> bool:
    """按证券简称判定风险警示股。

    ST/*ST 是交易所的风险警示标识；带「退」的是退市整理期。
    注意用大写比较，简称里偶有小写 st。
    """
    upper = name.upper().replace(" ", "")
    if "ST" in upper:
        return True
    return name.endswith("退") or "退市" in name


def fetch() -> dict[str, dict]:
    """返回 {code: {name, st}}。

    优先走**交易所官网**（深交所 A股列表 / 上交所主板+科创板 / 北交所）：
    这是证券简称的权威来源，而且不跟东财的频率限制抢资源；
    全部失败时才回退到东财实时行情。
    """
    import akshare as ak

    pairs: list[tuple[str, str]] = []
    sources = (
        ("stock_info_sz_name_code", {"symbol": "A股列表"}, "A股代码", "A股简称"),
        ("stock_info_sh_name_code", {"symbol": "主板A股"}, "证券代码", "证券简称"),
        ("stock_info_sh_name_code", {"symbol": "科创板"}, "证券代码", "证券简称"),
        ("stock_info_bj_name_code", {}, "证券代码", "证券简称"),
    )
    for fn, kwargs, code_col, name_col in sources:
        try:
            df = getattr(ak, fn)(**kwargs)
        except Exception as exc:  # noqa: BLE001 - 单个交易所失败不影响其他
            print(f"{fn}{kwargs} 失败：{type(exc).__name__}", file=sys.stderr)
            continue
        pairs += [(str(r[code_col]), str(r[name_col])) for _, r in df.iterrows()]
        print(f"{fn}{kwargs} → {len(df)} 条")

    if len(pairs) < 3000:
        print("交易所源不够，回退东财实时行情源", file=sys.stderr)
        df = ak.stock_zh_a_spot_em()
        pairs += [(str(r["代码"]), str(r["名称"])) for _, r in df.iterrows()]

    out: dict[str, dict] = {}
    for code, name in pairs:
        code = code.strip()
        # 交易所表里的简称带全角空格（如「万  科Ａ」），统一去掉
        clean = name.replace("\u3000", "").replace(" ", "").strip()
        if not code or len(code) != 6 or not code.isdigit() or not clean:
            continue
        out.setdefault(code, {"name": clean, "st": is_st_name(clean)})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="抓 A股代码→名称（含 ST 标记）")
    ap.add_argument("--out", default=str(ROOT / "data" / "stock_names.json"))
    args = ap.parse_args(argv)

    try:
        stocks = fetch()
    except Exception as exc:  # noqa: BLE001
        print(f"抓取失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if len(stocks) < 3000:
        print(f"结果只有 {len(stocks)} 只，明显不完整，放弃写入", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of": date.today().isoformat(),
        "count": len(stocks),
        "stocks": stocks,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    st_count = sum(1 for v in stocks.values() if v["st"])
    print(f"已写入 {out}：{len(stocks)} 只，其中风险警示（ST/退市）{st_count} 只")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
