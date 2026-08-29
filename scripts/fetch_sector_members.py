#!/usr/bin/env python3
"""阶段 11 第 2 段：东财行业板块成分拉取（当前快照）。

背景：sector_stocks.json 找不到（Obsidian vault 路径未知），AKShare 主接口
（17/29.push2.eastmoney.com）在本机被断连，但延迟镜像
push2delay.eastmoney.com 可用，且返回同一套数据格式。故本脚本绕过 akshare，
直接打延迟镜像，串行拉取「申万一级风格的 32 个粗粒度行业 + 高速公路」的
当前成分股，落盘 data/sector_members.json。

⚠️ 这是「当前」成分快照，回测 2023/2024 有成分变动 → 幸存者偏差（见报告坑①）。

速率纪律：串行 + 每次间隔 ≥1 秒；遇 429/超时/断连退避重试，最多 3 次。

用法（仓库根目录）：
    .venv/bin/python scripts/fetch_sector_members.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sector_members.json"

BASE = "https://push2delay.eastmoney.com/api/qt/clist/get"
UT = "bd1d9ddb04089700cf9c27f6f7426281"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
}
FIELDS = "f12,f14"
SLEEP_SEC = 1.2
MAX_RETRY = 3

# 申万一级风格的 32 个粗粒度行业（东财一级板块代码）+ 高速公路（高股息篮子用）。
SECTORS: list[tuple[str, str]] = [
    ("BK1283", "银行"),
    ("BK1203", "非银金融"),
    ("BK1204", "国防军工"),
    ("BK1211", "汽车"),
    ("BK1207", "计算机"),
    ("BK1215", "通信"),
    ("BK1216", "医药生物"),
    ("BK1201", "电子"),
    ("BK1200", "电力设备"),
    ("BK1205", "机械设备"),
    ("BK1206", "基础化工"),
    ("BK1208", "建筑材料"),
    ("BK1209", "建筑装饰"),
    ("BK1212", "轻工制造"),
    ("BK1213", "商贸零售"),
    ("BK1214", "社会服务"),
    ("BK1210", "交通运输"),
    ("BK1202", "房地产"),
    ("BK1217", "综合"),
    ("BK0438", "食品饮料"),
    ("BK0478", "有色金属"),
    ("BK0479", "钢铁"),
    ("BK0486", "传媒"),
    ("BK0433", "农林牧渔"),
    ("BK0427", "公用事业"),
    ("BK0436", "纺织服饰"),
    ("BK0437", "煤炭"),
    ("BK0428", "电力"),
    ("BK0464", "石油石化"),
    ("BK0456", "家用电器"),
    ("BK1035", "美容护理"),
    ("BK0728", "环保"),
    ("BK1483", "高速公路"),
]


def fetch_page(board: str, pn: int, pz: int = 100) -> dict:
    params = {
        "pn": str(pn), "pz": str(pz), "po": "1", "np": "1",
        "ut": UT, "fltt": "2", "invt": "2", "fid": "f3",
        "fs": f"b:{board}", "fields": FIELDS,
    }
    r = requests.get(BASE, params=params, headers=HEADERS, verify=False, timeout=30)
    if r.status_code == 429:
        raise RuntimeError("429")
    r.raise_for_status()
    return r.json()


def fetch_board(board: str) -> list[tuple[str, str]]:
    """串行 + 分页拉取单个板块全部成分，返回 [(code, name)]。"""
    members: list[tuple[str, str]] = []
    pn = 1
    while True:
        for attempt in range(1, MAX_RETRY + 1):
            try:
                j = fetch_page(board, pn)
                break
            except Exception as e:  # noqa: BLE001
                if attempt == MAX_RETRY:
                    raise
                wait = 3 * attempt
                print(f"  [retry] {board} pn={pn} {type(e).__name__} 退避 {wait}s", file=sys.stderr)
                time.sleep(wait)
        data = j.get("data") or {}
        diffs = data.get("diff") or []
        if not diffs:
            break
        members.extend((d.get("f12"), d.get("f14")) for d in diffs if d.get("f12"))
        total = int(data.get("total") or 0)
        if len(members) >= total or len(diffs) < 100:
            break
        pn += 1
        time.sleep(0.3)
    return members


def main() -> None:
    result: dict = {"source": "push2delay.eastmoney.com (东财行业板块, 当前快照)", "sectors": {}}
    total_members = 0
    for i, (code, name) in enumerate(SECTORS, 1):
        try:
            members = fetch_board(code)
        except Exception as e:  # noqa: BLE001
            print(f"[FAIL] {code} {name}: {type(e).__name__} {str(e)[:120]}", file=sys.stderr)
            result["sectors"][code] = {"name": name, "error": f"{type(e).__name__}: {str(e)[:200]}", "members": []}
        else:
            result["sectors"][code] = {"name": name, "members": [{"code": c, "name": n} for c, n in members]}
            total_members += len(members)
            print(f"[{i}/{len(SECTORS)}] {code} {name}: {len(members)} 只")
        time.sleep(SLEEP_SEC)

    result["summary"] = {
        "n_sectors": len(SECTORS),
        "n_sectors_ok": sum(1 for s in result["sectors"].values() if not s.get("error")),
        "total_members": total_members,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "note": "当前成分快照，回测历史有幸存者偏差",
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n已落盘 {OUT}（{result['summary']['n_sectors_ok']}/{len(SECTORS)} 板块，{total_members} 成分）")


if __name__ == "__main__":
    main()
