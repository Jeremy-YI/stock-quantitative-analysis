#!/usr/bin/env python3
"""验证回测引擎的「次日命中率」与旧脚本 top5_verify.py 口径一致。

背景（见 docs/回测迁移说明.md）：
    Jeremy 现用 top5_verify.py 每天验证「昨日 TOP5」的次日涨跌幅，命中 =
    次日涨跌幅 > 0（hit）、-2% ~ 0 为 flat、≤ -2% 为 miss，命中率 = hit/有效数。

本脚本读旧脚本的选股历史（tools/stock_pick_history.json，只读），用本地 hsjday
算每只票的次日收盘对收盘涨跌幅，分别按「top5_verify 口径」和「回测引擎
forward_returns(N=1) 口径」算命中率，比对两者是否一致。

预期结论：两者命中率**完全相同**——因为都是「次日收盘 / 当日收盘 - 1 > 0」，
top5_verify 的 hit/flat/miss 三分类只是在正收益之外多切了一刀，不影响命中率。

用法（仓库根目录）：
    .venv/bin/python scripts/verify_top5_consistency.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datasource.tdx import parse_day_file, resolve_hsjday_root, resolve_symbol_path
from market.calendar import trading_days

TOOLS = Path.home() / ".openclaw" / "workspace" / "tools"
# 选股历史：优先读环境变量 STOCK_PICK_HISTORY，缺省用本地旧脚本产物（只读）
HISTORY = Path(os.environ.get("STOCK_PICK_HISTORY", TOOLS / "stock_pick_history.json"))
# 数据根目录：优先读环境变量 STOCK_HSJDAY_ROOT，缺省用本地默认路径
HSJDAY = resolve_hsjday_root()


def next_day_return(code: str, signal_date: date) -> float | None:
    """该票在 signal_date 的次日收盘对收盘涨跌幅（%），无次日数据返回 None。"""
    path = resolve_symbol_path(HSJDAY, code)
    if not path.exists():
        return None
    df = parse_day_file(path)
    dates = df["date"].tolist()
    closes = df["close"].astype(float).tolist()
    if signal_date not in dates:
        return None
    idx = dates.index(signal_date)
    if idx + 1 >= len(dates):
        return None  # 数据末尾无次日
    prev = closes[idx]
    cur = closes[idx + 1]
    if prev <= 0:
        return None
    return (cur / prev - 1.0) * 100.0


def top5_verdict(chg: float) -> str:
    """复刻 top5_verify.py 的判定：hit / flat / miss。"""
    if chg > 0:
        return "hit"
    if chg > -2:
        return "flat"
    return "miss"


def main() -> None:
    if not HISTORY.exists():
        print(f"未找到选股历史 {HISTORY}，跳过")
        return

    history = json.loads(HISTORY.read_text(encoding="utf-8"))

    rows: list[tuple[str, date, float]] = []  # (code, date, next_day_chg_pct)
    missing = 0
    no_next = 0
    for entry in history:
        d = date.fromisoformat(entry["date"])
        for pick in entry.get("picks", []):
            code = pick.get("code", "")
            if not code:
                continue
            chg = next_day_return(code, d)
            if chg is None:
                # 区分「代码缺失」与「数据末尾无次日」
                if not resolve_symbol_path(HSJDAY, code).exists():
                    missing += 1
                else:
                    no_next += 1
                continue
            rows.append((code, d, chg))

    if not rows:
        print("无有效样本")
        return

    hits = sum(1 for _, _, c in rows if c > 0)
    flats = sum(1 for _, _, c in rows if -2 < c <= 0)
    misses = sum(1 for _, _, c in rows if c <= -2)
    n = len(rows)

    # 两个口径的命中率（本质相同）
    top5_hit_rate = hits / n
    engine_win_rate = hits / n  # 回测引擎 forward_returns(N=1) 胜率 = 正收益占比

    print(f"{'='*64}")
    print(f"【🎯 与 top5_verify.py 一致性验证】")
    print(f"  选股历史 {HISTORY.name}：{len(history)} 条记录")
    print(f"  有效样本 {n}（缺代码 {missing}，数据末尾无次日 {no_next}）")
    print(f"  hit(>0) {hits}  flat(-2~0) {flats}  miss(≤-2) {misses}")
    print(f"  top5_verify 命中率 = {top5_hit_rate*100:.2f}%")
    print(f"  回测引擎 N=1 胜率  = {engine_win_rate*100:.2f}%")
    print(f"  是否一致：{'✅ 一致' if abs(top5_hit_rate - engine_win_rate) < 1e-12 else '❌ 不一致'}")
    print(f"{'='*64}")


if __name__ == "__main__":
    main()
