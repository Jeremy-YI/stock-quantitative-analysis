#!/usr/bin/env python3
"""更新 data/news.json：抓金十快讯 → 映射成前端 / RAG 能用的消息结构。

用法（项目根目录）：
    .venv/bin/python scripts/update_news.py

数据源：金十 flash-api（实时财经快讯，标题级）。
说明：金十只给「标题级」快讯，不含深度解读/相关标的，故 outlook / related_symbols
      留空；后续可接大模型富化，或换更完整的数据源。可配合定时任务（财经快讯 cron）跑。
"""

from __future__ import annotations

import hashlib
import json
import re
import ssl
import sys
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

API_URL = "https://flash-api.jin10.com/get_flash_list?channel=-8200&vip=1"
HEADERS = {
    "x-app-id": "bVBF4FyRTn5NJF5n",
    "x-version": "1.0.0",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://www.jin10.com/",
}

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "news.json"

# 主题分类关键词（与 workspace tools/jin10_fetch.py 一致）
KEYWORDS = {
    "宏观": ["央行", "美联储", "CPI", "GDP", "PMI", "通胀", "利率", "国债", "汇率", "人民币", "美元",
             "加息", "降息", "就业", "财政", "关税", "贸易", "制裁", "财政部", "发改委", "商务部",
             "以色列", "伊朗", "中东", "俄罗斯", "乌克兰", "地缘", "战争", "冲突", "霍尔木兹"],
    "产业": ["AI", "半导体", "芯片", "新能源", "光伏", "电池", "汽车", "科技", "互联网",
             "数据中心", "大数据", "算力", "大模型", "光模块", "通信", "锂", "储能", "机器人"],
    "市场": ["A股", "沪指", "深指", "创业板", "恒生", "美股", "纳指", "标普", "道指", "期货", "原油",
             "黄金", "商品", "资金", "板块", "ETF", "成交", "回购", "北向"],
    "公司": ["公告", "业绩", "营收", "净利润", "减持", "增持", "回购", "IPO", "上市", "股价", "涨停",
             "跌停", "评级", "中标", "合同", "订单"],
}

# 非财经内容过滤（体育/娱乐/社会案件等）
BLOCKLIST = [
    "枪击", "枪杀", "命案", "谋杀", "火灾", "爆炸案",
    "足球", "篮球", "网球", "游泳", "田径", "奥运会", "世界杯", "联赛", "球队",
    "娱乐", "明星", "绯闻", "综艺", "演唱会", "电影票房", "电视剧",
    "地震", "台风", "洪水", "火山",
    "选举", "投票", "国会", "议会", "抗议", "游行", "示威", "骚乱",
    "车祸", "空难", "沉船",
]


def _clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"金十数据\d+月\d+日讯[，,]?\s*", "", s)
    return s.strip()


def _fetch(limit: int = 20) -> list[tuple[str, str, int]]:
    req = Request(API_URL, headers=HEADERS)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urlopen(req, timeout=15, context=ctx) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ 金十抓取失败: {exc}", file=sys.stderr)
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"⚠️ 金十 JSON 解析失败: {exc}", file=sys.stderr)
        return []

    if data.get("status") != 200:
        print(f"⚠️ 金十返回异常: {data.get('message')}", file=sys.stderr)
        return []

    items: list[tuple[str, str, int]] = []
    seen: set[str] = set()
    for it in data.get("data", []):
        body = it.get("data", {})
        content = _clean(body.get("content") or "")
        if not content:
            continue
        cid = it.get("id") or content[:32]
        if cid in seen:
            continue
        seen.add(cid)
        items.append((content, it.get("time", ""), it.get("important", 0)))
        if len(items) >= limit:
            break
    return items


def _relevant(content: str) -> bool:
    return not any(kw in content for kw in BLOCKLIST)


def _classify(content: str) -> str:
    for cat, kws in KEYWORDS.items():
        if any(kw in content for kw in kws):
            return cat
    return "市场"


def _title(content: str, maxlen: int = 50) -> str:
    return content[:maxlen] + ("…" if len(content) > maxlen else "")


def main() -> None:
    items = _fetch()
    if not items:
        print("⚠️ 金十抓取为空，未更新")
        sys.exit(1)

    news = []
    for content, _time, important in items:
        if not _relevant(content):
            continue
        news.append(
            {
                "id": hashlib.md5(content.encode("utf-8")).hexdigest()[:12],
                "title": _title(content),
                "impact": "显著影响" if important else "结构性关注",
                "level": "P1" if important else "P2",
                "outlook": "",
                "sources": 1,
                "detail": content,
                "topics": [_classify(content)],
                "related_symbols": [],
            }
        )

    if not news:
        print("⚠️ 过滤后无有效财经快讯，未更新")
        sys.exit(1)

    # 重要（P1）排前面
    news.sort(key=lambda x: 0 if x["level"] == "P1" else 1)

    payload = {
        "date": date.today().isoformat(),
        "source": "金十数据 flash-api（实时快讯）",
        "items": news,
    }
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"✅ 已更新 {OUT.name}：{len(news)} 条（日期 {payload['date']}）")


if __name__ == "__main__":
    main()
