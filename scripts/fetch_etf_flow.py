#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取场内 ETF 资金流，落盘 data/etf_flow.json（供 API 读取）。

为什么单独做：板块资金那张表里「对应 ETF」是靠名称匹配猜的，很多行业压根没有对应
ETF（猜不到就该留空，不该硬写）。真正有用的是**ETF 自己的资金流排行**，所以拆成
独立模块：板块资金看行业，ETF 资金流看可直接买的标的。

两个口径：
  net       主力净流入（东财大单口径，亿元）—— 盘口强弱，当天就有
  share_net 份额变化 × 最新价（亿元）—— 申购赎回的真金白银，需要隔天对比份额

份额历史存在 data/etf_shares_history.json（{日期: {代码: 份额}}，只留最近 30 天）。
首次运行没有历史，share_net 为 null，第二天开始就有。

用法：python3 scripts/fetch_etf_flow.py [--out data/etf_flow.json] [--top 20]
依赖：akshare（用系统 python3 跑，API 的 venv 不装）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 排除的品种：这些不是「买板块」的载体，混进排行只会干扰
EXCLUDE_KEYWORDS = (
    "货币",
    "债",
    "国债",
    "政金",
    "同业存单",
    "短融",
    # 场内货币基金（名字里不带「货币」，但本质是现金管理工具）
    "添益",
    "添利",
    "日利",
    "保证金",
    "现金",
    "理财",
    "快线",
)

# 过滤门槛（太小的 ETF 流动性差，净流入几百万没有意义）
MIN_MCAP_YI = 1.0      # 流通市值 ≥ 1 亿
MIN_TURNOVER_YI = 0.05  # 成交额 ≥ 500 万

HISTORY_PATH = ROOT / "data" / "etf_shares_history.json"
HISTORY_KEEP_DAYS = 30

# 东财快照在非交易日（周末/盘前）只给存量字段：价格/成交额/主力净流入全是 NaN，
# 只有流通市值和份额还在。这种快照绝不能覆盖上一个交易日的数据。
MIN_ACTIVE_ROWS = 100

# 主题分类：(大类, 主题, 命中关键词, 排除关键词)。顺序即优先级，具体的写在前面
# （"科创半导体ETF" 要落到半导体，不能被 "科创" 抢走）。
# 排除关键词用来拦策略变种（"A500红利ETF" 不算宽基，"黄金股" 不算商品黄金）。
# 每个主题最后只留资金最多（流通市值最大）的那一只，作为可交易的代表标的。
STRATEGY_WORDS = ("红利", "低波", "价值", "成长", "增强", "策略", "等权", "自由现金流")

THEMES: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    # ---------------- 宽基 ----------------
    ("宽基", "沪深300", ("沪深300", "300ETF"), STRATEGY_WORDS),
    ("宽基", "上证50", ("上证50",), STRATEGY_WORDS),
    ("宽基", "上证180", ("上证180",), STRATEGY_WORDS + ("金融",)),
    ("宽基", "中证500", ("中证500", "500ETF"), STRATEGY_WORDS + ("A500",)),
    ("宽基", "中证1000", ("中证1000", "1000ETF"), STRATEGY_WORDS),
    ("宽基", "中证2000", ("中证2000", "2000ETF"), STRATEGY_WORDS),
    ("宽基", "中证A500", ("A500", "中证A50"), STRATEGY_WORDS),
    ("宽基", "创业板", ("创业板",), STRATEGY_WORDS + ("人工智能", "医药", "新能源")),
    ("宽基", "科创50", ("科创50",), STRATEGY_WORDS),
    ("宽基", "科创100/综指", ("科创100", "科创综指", "科创板"), STRATEGY_WORDS),
    ("宽基", "深证100", ("深证100", "深100"), STRATEGY_WORDS),
    ("宽基", "北证/微盘", ("北证", "微盘"), ()),
    # ---------------- 科技成长 ----------------
    ("科技成长", "半导体/芯片", ("半导体", "芯片", "集成电路"), ()),
    ("科技成长", "人工智能/算力", ("人工智能", "AI", "算力", "云计算", "数据中心"), ()),
    ("科技成长", "通信/5G", ("通信", "5G"), ()),
    ("科技成长", "软件/计算机", ("软件", "计算机", "信创"), ()),
    ("科技成长", "消费电子/元件", ("消费电子", "电子", "光模块", "PCB"), ()),
    ("科技成长", "机器人/智能制造", ("机器人", "智能制造", "自动化"), ()),
    ("科技成长", "军工/国防", ("军工", "国防", "航天", "航空装备"), ()),
    ("科技成长", "新能源车/电池", ("新能源车", "电池", "锂电", "汽车"), ()),
    ("科技成长", "光伏", ("光伏",), ()),
    ("科技成长", "储能/风电", ("储能", "风电", "绿电"), ()),
    ("科技成长", "游戏/传媒", ("游戏", "传媒", "动漫", "影视"), ()),
    # ---------------- 医药消费 ----------------
    ("医药消费", "创新药", ("创新药", "生物医药"), ()),
    ("医药消费", "医疗/器械", ("医疗", "器械"), ()),
    ("医药消费", "医药", ("医药", "中药"), ()),
    ("医药消费", "白酒/食品饮料", ("白酒", "酒ETF", "食品饮料", "食品"), ()),
    ("医药消费", "消费/家电", ("消费", "家电", "零售"), ()),
    ("医药消费", "农业/养殖", ("农业", "养殖", "畜牧", "粮食"), ()),
    ("医药消费", "旅游/服务", ("旅游", "酒店", "航空运输"), ()),
    # ---------------- 金融地产 ----------------
    ("金融地产", "券商", ("证券", "券商"), ()),
    ("金融地产", "银行", ("银行",), ()),
    ("金融地产", "保险", ("保险",), ()),
    ("金融地产", "金融科技", ("金融科技", "科技金融"), ()),
    ("金融地产", "地产/建筑", ("地产", "建筑", "基建"), ()),
    # ---------------- 周期资源 ----------------
    ("周期资源", "黄金股", ("黄金股",), ()),
    ("周期资源", "黄金（商品）", ("黄金",), ("黄金股",)),
    ("周期资源", "有色/工业金属", ("有色", "工业金属", "稀有金属", "铜"), ()),
    ("周期资源", "稀土/新材料", ("稀土", "新材料"), ()),
    ("周期资源", "煤炭/能源", ("煤炭", "能源", "石油", "油气"), ()),
    ("周期资源", "钢铁/建材", ("钢铁", "建材", "水泥"), ()),
    ("周期资源", "化工", ("化工", "化学", "农化"), ()),
    ("周期资源", "电力/公用", ("电力", "公用", "环保"), ()),
    # ---------------- 红利防御 ----------------
    ("红利防御", "红利低波", ("红利低波", "低波"), ()),
    ("红利防御", "红利", ("红利", "股息"), ()),
    # ---------------- 跨境 ----------------
    ("跨境", "恒生科技", ("恒生科技", "港股科技"), ()),
    ("跨境", "中概互联", ("中概", "互联网"), ()),
    ("跨境", "港股通/恒生", ("港股", "恒生", "H股"), ()),
    ("跨境", "纳指/美股", ("纳指", "纳斯达克", "标普", "美国"), ()),
    ("跨境", "日经/亚太", ("日经", "日本", "亚太", "东南亚", "德国", "法国", "沙特"), ()),
)


def classify(name: str) -> tuple[str, str] | None:
    """ETF 名称 → (大类, 主题)。认不出来返回 None（不硬塞分类）。"""
    for category, theme, keywords, excludes in THEMES:
        if any(x in name for x in excludes):
            continue
        if any(k in name for k in keywords):
            return category, theme
    return None


def pick_leaders(rows: list[dict]) -> list[dict]:
    """每个主题只留一只代表：流通市值最大（并列时看成交额）。

    参考站点是把同一指数下所有 ETF 全列出来，那个粒度对做决策没必要——
    同一主题买哪只都差不多，只需要盯资金最集中的那只。
    """
    best: dict[str, dict] = {}
    peers: dict[str, int] = {}

    for r in rows:
        hit = classify(r["name"])
        if not hit:
            continue
        category, theme = hit
        peers[theme] = peers.get(theme, 0) + 1
        cur = best.get(theme)
        if cur is None or (r["mcap"], r["turnover"]) > (cur["mcap"], cur["turnover"]):
            best[theme] = {**r, "category": category, "theme": theme}

    # 按 THEMES 里的顺序输出，前端就不用再排（分类顺序是有讲究的：宽基→成长→…）
    order = {theme: i for i, (_, theme, _, _) in enumerate(THEMES)}
    leaders = sorted(best.values(), key=lambda x: order.get(x["theme"], 999))
    for item in leaders:
        item["peers"] = peers.get(item["theme"], 1)
    return leaders


def _f(value, default: float = 0.0) -> float:
    """安全转 float（akshare 里会有 '-' 和 NaN）。"""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out:  # NaN
        return default
    return out


def _load_history() -> dict[str, dict[str, float]]:
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_history(history: dict[str, dict[str, float]]) -> None:
    # 只留最近 N 天，避免文件无限长
    keys = sorted(history)[-HISTORY_KEEP_DAYS:]
    trimmed = {k: history[k] for k in keys}
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(trimmed, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )


def fetch(top: int = 20) -> dict:
    """抓一次全市场 ETF 快照，返回 {date, leaders, top_inflow, top_outflow, total}。

    非交易日（成交额全空）会抛 RuntimeError，由 main() 决定是保留旧快照还是走降级重建。
    """
    import akshare as ak  # 延迟导入：没装 akshare 时报错更清楚

    df = ak.fund_etf_spot_em()
    if df is None or df.empty:
        raise RuntimeError("fund_etf_spot_em 返回空")

    active = sum(1 for v in df.get("成交额", []) if _f(v) > 0)
    if active < MIN_ACTIVE_ROWS:
        raise RuntimeError(
            f"非交易日快照（有成交的只有 {active} 只），不能当作当日行情用"
        )

    data_date = str(df["数据日期"].dropna().iloc[0])[:10] if "数据日期" in df else ""

    history = _load_history()
    prev_shares: dict[str, float] = {}
    prev_days = [d for d in sorted(history) if d < data_date]
    if prev_days:
        prev_shares = history[prev_days[-1]]

    today_shares: dict[str, float] = {}
    rows: list[dict] = []

    for _, r in df.iterrows():
        name = str(r.get("名称", ""))
        code = str(r.get("代码", ""))
        if not code or any(k in name for k in EXCLUDE_KEYWORDS):
            continue

        mcap_yi = _f(r.get("流通市值")) / 1e8
        turnover_yi = _f(r.get("成交额")) / 1e8
        shares = _f(r.get("最新份额"))
        price = _f(r.get("最新价"))

        # 兜底识别货币类：净值 ~100 且几乎不波动（关键词漏网时靠这条拦下）
        if price > 50 and abs(_f(r.get("涨跌幅"))) < 0.1:
            continue

        if shares > 0:
            today_shares[code] = shares
        if mcap_yi < MIN_MCAP_YI or turnover_yi < MIN_TURNOVER_YI:
            continue

        # 份额变化 → 估算净申购（亿元）。份额单位是「份」，乘最新价得金额。
        share_net = None
        prev = prev_shares.get(code)
        if prev and prev > 0 and shares > 0 and price > 0:
            share_net = round((shares - prev) * price / 1e8, 4)

        rows.append(
            {
                "code": code,
                "name": name,
                "price": round(price, 3),
                "change_pct": round(_f(r.get("涨跌幅")), 2),
                "net": round(_f(r.get("主力净流入-净额")) / 1e8, 4),
                "net_ratio": round(_f(r.get("主力净流入-净占比")), 2),
                "turnover": round(turnover_yi, 3),
                "turnover_rate": round(_f(r.get("换手率")), 2),
                "mcap": round(mcap_yi, 2),
                "share_net": share_net,
            }
        )

    if data_date and today_shares:
        history[data_date] = today_shares
        _save_history(history)

    inflow = sorted(rows, key=lambda x: x["net"], reverse=True)[:top]
    outflow = sorted(rows, key=lambda x: x["net"])[:top]

    return {
        "date": data_date,
        "total": len(rows),
        "has_share_flow": bool(prev_shares),
        "leaders": pick_leaders(rows),
        "top_inflow": inflow,
        "top_outflow": outflow,
    }


def _read_tdx_last_bars(
    code: str, root: Path, ref_price: float = 0.0
) -> tuple[str, float, float, float] | None:
    """从本地通达信日线读最后两根，返回 (日期, 收盘, 涨跌幅%, 成交额亿)。

    为什么不走网络：东财 fund_etf_hist_em 连续请求会直接断连，而本地 hsjday 本来
    就是全市场日线（含 ETF），读盘更快也更稳。

    通达信 .day 格式：每 32 字节一根，<日期 i, 开 i, 高 i, 低 i, 收 i, 额 f, 量 i, 保留 i>。
    坑：个股价格是 ×100，**基金/ETF 是 ×1000**。这里用 ref_price（由流通市值/份额
    算出的近似净值）自动选比例，避开写死判断。
    """
    prefix = "sh" if code.startswith(("5", "6", "9", "11", "13")) else "sz"
    path = root / prefix / "lday" / f"{prefix}{code}.day"
    if not path.exists():
        other = "sz" if prefix == "sh" else "sh"
        path = root / other / "lday" / f"{other}{code}.day"
        if not path.exists():
            return None

    raw = path.read_bytes()
    if len(raw) < 64:
        return None
    import struct

    last = struct.unpack("<IiiiifIi", raw[-32:])
    prev = struct.unpack("<IiiiifIi", raw[-64:-32])
    date = str(last[0])

    close_raw = float(last[4])
    prev_raw = float(prev[4])
    # 选比例：距参考净值更近的那个（没参考值时默认 ETF 的 1000）
    divisor = 1000.0
    if ref_price > 0:
        divisor = min(
            (100.0, 1000.0),
            key=lambda d: abs(close_raw / d - ref_price) / ref_price,
        )

    close = close_raw / divisor
    prev_close = prev_raw / divisor
    amount_yi = last[5] / 1e8
    change_pct = ((close - prev_close) / prev_close * 100) if prev_close else 0.0
    return f"{date[:4]}-{date[4:6]}-{date[6:]}", close, change_pct, amount_yi


def rebuild_leaders_from_stock(hsjday_root: str | None = None) -> dict:
    """降级重建（非交易日且本地没快照时用）。

    周末快照只剩存量字段（流通市值/份额），所以：
      1. 用流通市值选出各主题龙头
      2. 从本地通达信日线补上上一交易日的收盘/涨跌幅/成交额
      3. 主力净流入是实时大单口径，历史不可回溯 → 置 None，前端显示「—」
    宁可留空，也不造假数。
    """
    import akshare as ak

    root = Path(
        hsjday_root
        or os.environ.get("STOCK_HSJDAY_ROOT")
        or (Path.home() / "Desktop" / "每日复盘" / "hsjday")
    )

    df = ak.fund_etf_spot_em()
    rows: list[dict] = []
    for _, r in df.iterrows():
        name = str(r.get("名称", ""))
        code = str(r.get("代码", ""))
        if not code or any(k in name for k in EXCLUDE_KEYWORDS):
            continue
        mcap_yi = _f(r.get("流通市值")) / 1e8
        if mcap_yi < MIN_MCAP_YI:
            continue
        shares = _f(r.get("最新份额"))
        # 近似净值 = 流通市值 / 份额，用来判定通达信价格比例（×100 还是 ×1000）
        ref_price = (mcap_yi * 1e8 / shares) if shares > 0 else 0.0
        rows.append(
            {
                "code": code,
                "name": name,
                "price": 0.0,
                "change_pct": 0.0,
                "net": None,
                "net_ratio": None,
                "turnover": 0.0,
                "turnover_rate": 0.0,
                "mcap": round(mcap_yi, 2),
                "share_net": None,
                "_ref_price": round(ref_price, 4),
            }
        )

    leaders = pick_leaders(rows)

    data_date = ""
    for item in leaders:
        bars = _read_tdx_last_bars(item["code"], root, item.get("_ref_price", 0.0))
        item.pop("_ref_price", None)
        if not bars:
            continue
        date, close, change_pct, amount_yi = bars
        item["price"] = round(close, 3)
        item["change_pct"] = round(change_pct, 2)
        item["turnover"] = round(amount_yi, 3)
        data_date = max(data_date, date)

    return {
        "date": data_date,
        "total": len(rows),
        "has_share_flow": False,
        "flow_available": False,  # 主力净流入不可回溯
        "leaders": leaders,
        "top_inflow": [],
        "top_outflow": [],
    }


def dump_universe(out: Path) -> None:
    """顺手落一份 ETF 名称表（代码→名称），给板块 ETF 匹配用（覆盖率比旧表高）。"""
    import akshare as ak

    df = ak.fund_etf_spot_em()
    mapping = {str(r["代码"]): str(r["名称"]) for _, r in df.iterrows()}
    out.write_text(json.dumps(mapping, ensure_ascii=False, indent=0), encoding="utf-8")


def build_snapshot(top: int, out: Path, force_rebuild: bool) -> dict | None:
    """组装要写入的快照。返回 None = 「保留已有快照，本次不覆盖」。"""
    if force_rebuild:
        print("强制降级重建（主题龙头 + 本地通达信日线，大单口径留空）…")
        return rebuild_leaders_from_stock()

    try:
        snapshot = fetch(top)
    except RuntimeError as exc:
        # 非交易日：有旧快照就保留（绝不用空数据覆盖），没有才降级重建
        print(f"跳过实时口径：{exc}", file=sys.stderr)
        if out.exists():
            try:
                old = json.loads(out.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                old = {}
            if (old.get("leaders") or old.get("top_inflow")) and old.get("date"):
                print(f"保留已有快照（{old.get('date')}），本次不覆盖。")
                return None
        print("本地无可用快照，走降级重建（主题龙头 + 上一交易日行情，资金流置空）…")
        return rebuild_leaders_from_stock()

    snapshot["flow_available"] = True
    return snapshot


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="抓 ETF 资金流快照")
    ap.add_argument("--out", default=str(ROOT / "data" / "etf_flow.json"))
    ap.add_argument("--universe-out", default=str(ROOT / "data" / "etf_universe.json"))
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument(
        "--rebuild",
        action="store_true",
        help="强制走降级重建（主题龙头 + 本地日线行情，资金流置空）",
    )
    args = ap.parse_args(argv)

    out = Path(args.out)

    try:
        snapshot = build_snapshot(args.top, out, args.rebuild)
    except Exception as exc:  # noqa: BLE001 - 脚本层要把网络异常变成退出码
        print(f"抓取失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if snapshot is None:
        return 0

    # 写入前先备份上一版，出事能回滚
    if out.exists():
        (out.parent / f"{out.stem}_prev.json").write_text(
            out.read_text(encoding="utf-8"), encoding="utf-8"
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")

    try:
        dump_universe(Path(args.universe_out))
    except Exception as exc:  # noqa: BLE001
        print(f"（ETF 名称表未更新：{type(exc).__name__}: {exc}）", file=sys.stderr)

    print(
        f"ETF 资金流快照已写入 {out}："
        f"{snapshot['date']} 有效 {snapshot['total']} 只，"
        f"主题龙头 {len(snapshot['leaders'])} 个，"
        f"大单口径 {'可用' if snapshot.get('flow_available') else '不可用（非交易日）'}，"
        f"份额口径 {'可用' if snapshot['has_share_flow'] else '待次交易日'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
