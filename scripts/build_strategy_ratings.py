#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把样本外回测结果（data/oos_strategies.json）编译成策略评级表。

为什么要这一步：策略能不能推荐给客户，**不能靠 Obsidian 里的笔记，只能靠回测**。
这个脚本把「四段区间（样本内 IS + 样本外 A/B/C）的 20 日超额胜率」按 docs/样本外验证报告.md
的判定标准机械地翻译成评级，落盘 data/strategy_ratings.json，供 API 过滤推荐。

判定标准（与报告 §1 一致，全部机械判定，不留人情）：
  robust        四段全正，且每段样本量 ≥ MIN_SAMPLES        → 可推荐给客户
  oos_positive  三段样本外全正（样本内可负），样本量达标      → 可推荐，标注「弱」
  regime        有正有负                                    → 仅内部（root）参考
  overfit       样本内正、样本外全负                          → 禁用
  insufficient  任一段样本量 < MIN_SAMPLES                    → 无法定论，仅 root
  no_edge       四段幅度都在 ±NO_EDGE_PP 内，或选择性过高      → 无区分度，禁用

另外单独维护一份「排除项」（放量滞涨 / 长上影 / 追高），这些在报告里是**稳健结论**
（「放量必差、追高必差」四段一致），所以作为硬过滤器写死，不参与评级。

用法：python3 scripts/build_strategy_ratings.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OOS_PATH = ROOT / "data" / "oos_strategies.json"
OUT_PATH = ROOT / "data" / "strategy_ratings.json"

# 样本量红线：低于这个数的区间不足以下结论（报告 §2 用的同一条线）
MIN_SAMPLES = 100
# 幅度门槛：四段都在 ±1pp 内视为没有区分度
NO_EDGE_PP = 0.01
# 选择性上限：每天触发超过这个比例的市场，等于「什么都推」
MAX_SELECTIVITY = 0.35

WINDOW_ORDER = ["IS", "OOS-A", "OOS-B", "OOS-C"]

# 评级 → 是否可以出现在给客户的推荐里
CLIENT_SAFE = {"robust", "oos_positive"}

LABELS = {
    "b1b2b3": "超卖反弹",
    "pin30": "单针",
    "stealth_rally": "偷涨",
    "double_bottom": "双底",
    "macd_resonance": "月周共振",
    "macd_volume_washout": "缩量洗盘",
    "etf_accumulation": "ETF抄底",
}


def classify(windows: dict[str, dict]) -> tuple[str, str]:
    """返回 (rating, reason)。windows: {区间: {excess_win_rate, n, selectivity}}。"""
    present = [w for w in WINDOW_ORDER if w in windows]
    if not present:
        return "unknown", "没有回测数据"

    excess = {w: windows[w]["excess_win_rate"] for w in present}
    samples = {w: windows[w].get("n", 0) for w in present}
    selectivity = max(windows[w].get("selectivity", 0.0) for w in present)

    thin = [w for w in present if samples[w] < MIN_SAMPLES]
    oos = [w for w in present if w != "IS"]

    all_positive = all(excess[w] > 0 for w in present)
    oos_all_positive = bool(oos) and all(excess[w] > 0 for w in oos)
    oos_all_negative = bool(oos) and all(excess[w] < 0 for w in oos)
    flat = all(abs(excess[w]) <= NO_EDGE_PP for w in present)

    detail = " / ".join(f"{w} {excess[w] * 100:+.1f}pp" for w in present)

    if selectivity > MAX_SELECTIVITY:
        return "no_edge", f"选择性过高（{selectivity:.0%}，等于每天推半个市场）：{detail}"
    if flat:
        return "no_edge", f"四段幅度都在 ±1pp 内，没有区分度：{detail}"
    if thin:
        return "insufficient", f"样本量不足（{', '.join(f'{w} n={samples[w]}' for w in thin)}）：{detail}"
    if all_positive:
        return "robust", f"四段全正：{detail}"
    if oos_all_positive:
        return "oos_positive", f"样本外三段全正（样本内为负）：{detail}"
    if oos_all_negative and excess.get("IS", 0) > 0:
        return "overfit", f"样本内正、样本外全负，判为过拟合：{detail}"
    return "regime", f"有正有负，环境依赖：{detail}"


def build() -> dict:
    raw = json.loads(OOS_PATH.read_text(encoding="utf-8"))

    per_strategy: dict[str, dict[str, dict]] = {}
    for window, blk in raw.items():
        for name, stats in (blk.get("strategies") or {}).items():
            per_strategy.setdefault(name, {})[window] = stats

    ratings = {}
    for name, windows in sorted(per_strategy.items()):
        rating, reason = classify(windows)
        ratings[name] = {
            "label": LABELS.get(name, name),
            "rating": rating,
            "client_safe": rating in CLIENT_SAFE,
            "reason": reason,
            "windows": {
                w: {
                    "excess_win_rate": windows[w]["excess_win_rate"],
                    "n": windows[w].get("n", 0),
                    "selectivity": windows[w].get("selectivity"),
                }
                for w in WINDOW_ORDER
                if w in windows
            },
        }

    # macd_resonance 没进 OOS 跑批（样本内 -12.9pp 已判死），显式登记为禁用
    if "macd_resonance" not in ratings:
        ratings["macd_resonance"] = {
            "label": LABELS["macd_resonance"],
            "rating": "overfit",
            "client_safe": False,
            "reason": "样本内 20 日超额 -12.9pp（全周期最差），未纳入样本外跑批，直接禁用",
            "windows": {},
        }

    return {
        "as_of": date.today().isoformat(),
        "source": "data/oos_strategies.json（阶段 9/10 四段样本外跑批）",
        "criteria": {
            "min_samples": MIN_SAMPLES,
            "no_edge_pp": NO_EDGE_PP,
            "max_selectivity": MAX_SELECTIVITY,
            "client_safe_ratings": sorted(CLIENT_SAFE),
        },
        "strategies": ratings,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="编译策略回测评级")
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args(argv)

    if not OOS_PATH.exists():
        print(f"缺少回测结果 {OOS_PATH}，先跑 scripts/run_oos_strategies.py", file=sys.stderr)
        return 1

    payload = build()
    out = Path(args.out)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"已写入 {out}")
    for name, info in payload["strategies"].items():
        flag = "可推荐" if info["client_safe"] else "仅内部"
        print(f"  {info['label']:<10} {name:<22} {info['rating']:<13} {flag}  {info['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
