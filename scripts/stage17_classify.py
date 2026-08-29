#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 17：ETF 分组分类（宽基/行业主题/商品/QDII/红利风格/债券货币）。

本地无 ETF 名称表，名称来自 akshare 快照（data/stage17_etf_names.json = fund_etf_spot_em +
fund_name_em 合并）。分类 = 名称关键词规则 + 显式 overrides（见 GROUP_OVERRIDES）。
债券货币（国债/地方债/公司债/政金债/可转债/货币/短融）不是「板块 ETF」，主分析里剔除。

用法：作为模块被 run_stage17.py 导入；也可独立跑 --dump 打印全表。
"""
from __future__ import annotations

# 显式覆盖（优先级最高）：code(6位) -> group。主要是名称歧义或规则覆盖不到的边角。
GROUP_OVERRIDES: dict[str, str] = {
    # 黄金股 = 黄金矿业股票，归行业（不是商品现货）
    "517520": "sector",
    # 有色期货 ETF（大成有色 = 商品期货），与「有色金属产业」股票 ETF 区分
    "159980": "commodity",
    # 石油 ETF（国泰/鹏华）= 原油期货 → 商品
    "561360": "commodity",
    "159697": "commodity",
    # 教育 ETF 博时 = 全球中国教育（QDII）
    "513360": "qdii",
    # 513960 不在任何名称表（已退市/更名 QDII，cl=1 仅 2023 一个月）
    "513960": "qdii",
    # 黄金股 ETF
    "518600": "commodity",  # 金ETF广发（现货金）
    "518680": "commodity",
    "518800": "commodity",
    "518880": "commodity",
    # 159962 无法在任何名称表解析到（cl=1，仅 2020-09 一个月）→ 归债券货币（剔除，无法验证为权益类）
    "159962": "bond",
}

BOND_KEYWORDS = ("债", "货币", "添益", "日利", "快线", "保证金", "短融", "财富宝")
COMMODITY_KEYWORDS = ("黄金", "金ETF", "豆粕", "能源化工", "白银", "石油", "原油", "上海金")
QDII_KEYWORDS = (
    "恒生", "港股", "纳指", "纳斯达克", "标普", "道琼斯", "日经", "日本", "东证",
    "德国", "法国", "英国", "东南亚", "中概", "中韩", "美国", "亚太", "巴西", "沙特",
    "教育", "海外", "全球", "香港", "新兴", "韩国", "越南", "印度", "欧洲", "MSCI",
    "沪港", "港币", "纳斯达克", "纳指",
)
STYLE_KEYWORDS = ("红利", "低波", "价值", "成长", "现金流", "质量", "高股息", "股息")
SECTOR_KEYWORDS = (
    "医药", "医疗", "生物", "创新药", "中药", "疫苗", "器械", "医械", "制药", "健康",
    "半导体", "芯片", "集成电路", "证券", "券商", "银行", "保险", "金融", "金科",
    "军工", "国防", "酒", "白酒", "食品", "饮料", "消费", "食饮",
    "新能源", "光伏", "电池", "储能", "充电", "氢能", "汽车", "智能汽车", "智能车",
    "智能驾驶", "驾驶", "稀土", "有色", "稀有金属", "金属", "贵金属", "煤炭", "钢铁",
    "房地产", "地产", "计算机", "通信", "传媒", "游戏", "电子", "人工智能", "机器人",
    "云计算", "软件", "信创", "大数据", "数字经济", "基建", "工程机械", "机械",
    "化工", "石化", "家电", "农业", "养殖", "种植", "粮食", "旅游", "建材", "电力",
    "电网", "绿电", "能源", "公用", "航空", "卫星", "工业母机", "母机", "核电", "船舶",
    "科技", "央企", "国企", "改革", "共赢", "结构", "创新", "低碳", "碳中和", "环保",
    "绿色", "新经济", "新材", "材料", "消费电子", "影视", "动漫", "传媒娱乐",
    "半导体设备", "光模块", "光通信", "非银", "证券保险", "电池", "储能电池",
    "芯片设计", "自由现金流",
)
BROAD_KEYWORDS = (
    "沪深300", "中证500", "中证1000", "中证2000", "上证50", "上证180", "上证指数",
    "深证100", "深证", "中证A", "中国A50", "A50", "A500", "创业板50", "科创50",
    "科创100", "科创200", "科创创业", "双创", "中小", "创业板", "科创板", "上证",
    "中证", "国证",
)

GROUP_LABELS = {
    "broad": "宽基",
    "sector": "行业主题",
    "commodity": "商品",
    "qdii": "QDII",
    "style": "红利风格",
    "bond": "债券货币",
}

# 权益类分组（剔除债券货币），主分析用
EQUITY_GROUPS = ("broad", "sector", "commodity", "qdii", "style")


def classify(code: str, name: str) -> str:
    """返回 group key（broad/sector/commodity/qdii/style/bond）。"""
    if code in GROUP_OVERRIDES:
        return GROUP_OVERRIDES[code]
    n = name or ""
    if any(k in n for k in BOND_KEYWORDS):
        return "bond"
    if any(k in n for k in COMMODITY_KEYWORDS):
        return "commodity"
    if any(k in n for k in QDII_KEYWORDS):
        return "qdii"
    if any(k in n for k in STYLE_KEYWORDS):
        return "style"
    if any(k in n for k in SECTOR_KEYWORDS):
        return "sector"
    if any(k in n for k in BROAD_KEYWORDS):
        return "broad"
    return "sector"  # 未命中归行业主题（默认偏保守，多数未知代码是板块/主题类）


def load_names() -> dict[str, str]:
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "data" / "stage17_etf_names.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def classify_symbol(sym: str, names: dict[str, str]) -> tuple[str, str]:
    """sym 形如 'sh510300' / 'sz159915'，返回 (group, name)。"""
    code = sym[2:]
    name = names.get(code, "")
    return classify(code, name), name


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT))
    from datasource.tdx.reader import resolve_hsjday_root

    names = load_names()
    d = json.loads((ROOT / "data" / "stage17_universe.json").read_text(encoding="utf-8"))
    ei = d["combinations"]["liq_50M_rho_0.95"]["ever_in"]

    from collections import Counter
    cnt = Counter()
    rows = []
    for sym in sorted(ei):
        g, name = classify_symbol(sym, names)
        cnt[g] += 1
        rows.append((sym, name, g))
    print("分组统计（liq_50M_rho_0.95 ever_in）:", dict(cnt))
    print()
    for sym, name, g in rows:
        print(f"{sym}  {name or '?'}  ->  {GROUP_LABELS[g]}")
