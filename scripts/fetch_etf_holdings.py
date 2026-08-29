#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 18：拉取目标 ETF（行业主题/宽基/红利风格）的最新股票持仓明细。

数据源：天天基金 F10 基金持仓接口（FundArchivesDatas.aspx?type=jjcc）。
akshare 的 fund_portfolio_hold_em 当前因缺 Referer 头 + demjson 解析失败而报错，
这里直接 requests 拉 + 正则抽 content + BeautifulSoup 解析表格。

输出：data/stage18_etf_holdings.json = {
  "meta": {...},
  "etfs": { code: {"name":..., "group":..., "report": "2026年2季度", "stocks": [6位代码...]} }
}
"""
from __future__ import annotations

import json
import re
import sys
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.stage17_classify import GROUP_LABELS, classify_symbol, load_names

TARGET_GROUPS = ("sector", "broad", "style")  # 行业主题 / 宽基 / 红利风格
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
YEAR = "2026"


def fetch_holdings(code: str, year: str = YEAR) -> tuple[str, list[str]]:
    """返回 (报告期标签, 股票代码列表)。失败返回 ("", [])。"""
    url = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
    params = {"type": "jjcc", "code": code, "topline": "10000",
              "year": year, "month": "", "rt": "0.913877"}
    headers = {"User-Agent": UA,
               "Referer": f"http://fundf10.eastmoney.com/ccmx_{code}.html"}
    r = requests.get(url, params=params, headers=headers, timeout=30)
    raw_bytes = r.content
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_bytes.decode("gbk", errors="replace")

    m = re.search(r'content:"(.*)",\s*arryear', text, re.S)
    if not m:
        # 兜底：找 content:" 到 结尾最近的 " 前
        m = re.search(r'content:"(.*)"', text, re.S)
    if not m:
        return "", []
    raw = m.group(1)
    # JS 字符串里的转义还原
    raw = raw.replace("\\\"", '"').replace("\\n", "\n").replace("\\/", "/")

    soup = BeautifulSoup(raw, "lxml")
    labels = [it.get_text(strip=True) for it in soup.find_all("h4", attrs={"class": "t"})]
    if not labels:
        return "", []
    # 最新一期报告 = 第一个 h4（页面上最新季度在最前）
    report = labels[0]

    try:
        tables = pd.read_html(StringIO(raw))
    except Exception:
        return report, []
    if not tables:
        return report, []
    df = tables[0]
    # 找「股票代码」列：表头可能因编码/改名而不确定，用「值全为 6 位数字」定位
    code_col = None
    for c in df.columns:
        vals = df[c].astype(str)
        if vals.str.fullmatch(r"\d{6}").sum() >= max(1, int(len(df) * 0.5)):
            code_col = c
            break
    if code_col is None:
        return report, []
    codes = [str(x).strip().zfill(6) for x in df[code_col].tolist()]
    codes = [c for c in codes if re.fullmatch(r"\d{6}", c)]
    return report, codes


def target_etfs() -> list[tuple[str, str, str]]:
    """从阶段17宇宙取 (code, name, group) 三组目标 ETF。"""
    names = load_names()
    d = json.loads((ROOT / "data" / "stage17_universe.json").read_text(encoding="utf-8"))
    ei = d["combinations"]["liq_50M_rho_0.95"]["ever_in"]
    out = []
    for sym in sorted(ei):
        g, name = classify_symbol(sym, names)
        if g in TARGET_GROUPS:
            out.append((sym[2:], name, g))
    return out


def main() -> None:
    etfs = target_etfs()
    print("目标 ETF %d 只（行业主题/宽基/红利风格）" % len(etfs))

    result = {}
    fail = []
    for i, (code, name, grp) in enumerate(etfs, 1):
        ok = False
        for attempt in range(3):
            try:
                report, stocks = fetch_holdings(code)
                ok = True
                break
            except Exception as e:
                if attempt == 2:
                    fail.append((code, name, grp, str(e)[:120]))
                time.sleep(1.0)
        if ok and stocks:
            result[code] = {"name": name, "group": grp,
                            "report": report, "n": len(stocks), "stocks": stocks}
        elif ok:
            fail.append((code, name, grp, "empty holdings"))
        else:
            pass  # fail 已记录
        if i % 20 == 0:
            print("  %d/%d 完成，成功 %d，失败 %d" % (i, len(etfs), len(result), len(fail)),
                  flush=True)
        time.sleep(0.25)

    all_stocks = sorted({s for v in result.values() for s in v["stocks"]})
    out = {"meta": {"source": "fundf10.eastmoney.com jjcc",
                    "year": YEAR,
                    "target_groups": {g: GROUP_LABELS[g] for g in TARGET_GROUPS},
                    "n_etf_ok": len(result),
                    "n_etf_fail": len(fail),
                    "n_unique_stocks": len(all_stocks),
                    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")},
           "etfs": result,
           "failures": [{"code": c, "name": n, "group": g, "err": e}
                        for c, n, g, e in fail],
           "all_stocks": all_stocks}

    out_path = ROOT / "data" / "stage18_etf_holdings.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("\n落盘 %s" % out_path)
    print("成功 ETF %d，失败 %d，唯一股票 %d" % (len(result), len(fail), len(all_stocks)))
    if fail:
        print("失败明细：")
        for c, n, g, e in fail:
            print("  %s %s [%s] %s" % (c, n, g, e))


if __name__ == "__main__":
    main()
