#!/usr/bin/env python3
"""更新 data/events.json：过滤掉已过去的事件，保留未来的宏观事件。

事件日历是「前瞻性日程」，不像新闻那样实时抓取。本脚本只做「修剪」：
把日期已过去的事件移除，保留未来要关注的。
要新增 / 修改事件，直接编辑 data/events.json（或告诉我，我来维护）。

用法（项目根目录）：
    .venv/bin/python scripts/update_events.py
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "events.json"

# 「上旬 / 中旬 / 下旬」映射到代表日（用于判断是否已过去）
_XUN = {"上旬": 5, "中旬": 15, "下旬": 25}


def _to_date(s: str) -> date | None:
    """把 'YYYY-MM-DD' 或 'YYYY-MM-下旬' 之类解析成 date。"""
    s = (s or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"^(\d{4})-(\d{2})-(上旬|中旬|下旬)$", s)
    if m:
        return date(int(m[1]), int(m[2]), _XUN[m[3]])
    return None


def main() -> None:
    raw = json.loads(OUT.read_text(encoding="utf-8"))
    events = raw.get("events", [])
    today = date.today()

    kept, pruned = [], []
    for ev in events:
        d = _to_date(ev.get("date", ""))
        if d is None or d >= today:
            kept.append(ev)
        else:
            pruned.append(ev.get("name", "?"))

    raw["events"] = kept
    raw["note"] = "事件日历（前瞻性宏观事件，手动维护 + 自动修剪已过去的）"
    OUT.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 事件日历已更新：保留 {len(kept)} 条，移除 {len(pruned)} 条已过去的")
    for p in pruned:
        print(f"   - 移除：{p}")


if __name__ == "__main__":
    main()
