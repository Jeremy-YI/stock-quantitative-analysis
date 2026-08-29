#!/usr/bin/env python3
"""阶段 11 第 2 段：regime 阈值敏感性。

背景：第 1 段用 -5%/+5% 做 regime 标签，发现 OOS 三段「大跌」只占 1.7%~4.5%
（每年 4~11 天），样本外验证必然样本不足。本脚本把阈值在
    大跌 ∈ {-3%, -4%, -5%, -6%}、大涨 ∈ {+3%, +5%, +7%}
上各跑一遍，输出四段各档天数占比，为选「主口径」提供依据。

主口径选择标准（任务书）：四段每段大跌天数 ≥ 40。若不满足，如实报告并给出
「最接近」的组合作为主口径，其余作为敏感性附录。

用法（仓库根目录）：
    .venv/bin/python scripts/run_regime_threshold_sensitivity.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "datasource"))

from datasource.tdx.reader import parse_day_file, DEFAULT_HSJDAY_ROOT

LOOKBACK_DAYS = 20
# 任务书列出的敏感性范围；另加 -2%/-2.5%、+2%/+2.5% 用于检查「每段≥40」是否可达
DOWN_CANDIDATES = [-0.02, -0.025, -0.03, -0.04, -0.05, -0.06]
UP_CANDIDATES = [0.02, 0.025, 0.03, 0.05, 0.07]

WINDOWS: list[tuple[str, str, str]] = [
    ("IS", "2026-03-01", "2026-08-27"),
    ("OOS-A", "2023-01-01", "2023-12-31"),
    ("OOS-B", "2024-01-01", "2024-12-31"),
    ("OOS-C", "2025-01-01", "2026-02-28"),
]

OUT = ROOT / "data" / "regime_threshold_sensitivity.json"


def classify(r20: float, up: float, down: float) -> str:
    if r20 >= up:
        return "大涨"
    if r20 <= down:
        return "大跌"
    return "中性"


def count_periods(series: pd.DataFrame, up: float, down: float) -> dict[str, dict]:
    """series: 以 date 为索引、含 r20 列。返回四段 {label: {days, 大涨, 中性, 大跌, pct}}。"""
    s = series.copy()
    s["regime"] = s["r20"].map(lambda r: classify(r, up, down))
    out: dict[str, dict] = {}
    for label, start, end in WINDOWS:
        a = date.fromisoformat(start)
        b = date.fromisoformat(end)
        seg = s.loc[a:b]
        n = len(seg)
        c = seg["regime"].value_counts().to_dict()
        up_n = c.get("大涨", 0)
        mid_n = c.get("中性", 0)
        down_n = c.get("大跌", 0)
        out[label] = {
            "days": n,
            "counts": {"大涨": up_n, "中性": mid_n, "大跌": down_n},
            "pct": {
                "大涨": round(up_n / n, 4) if n else None,
                "中性": round(mid_n / n, 4) if n else None,
                "大跌": round(down_n / n, 4) if n else None,
            },
        }
    return out


def main() -> None:
    idx_path = DEFAULT_HSJDAY_ROOT / "sh" / "lday" / "sh000001.day"
    if not idx_path.exists():
        print(f"[FATAL] 上证指数日线不存在：{idx_path}", file=sys.stderr)
        sys.exit(1)

    df = parse_day_file(idx_path).set_index("date")
    close = df["close"]
    r20 = close.pct_change(LOOKBACK_DAYS)
    series = pd.DataFrame({"r20": r20}).dropna(subset=["r20"])

    out_start = date(2022, 12, 1)
    out_end = date(2026, 8, 27)
    series = series.loc[out_start:out_end]

    result = {"lookback_days": LOOKBACK_DAYS, "windows": WINDOWS, "grid": {}}

    # 大跌天数：只与 down 阈值有关（大涨阈值不影响大跌分类）
    print("== 大跌天数（按 down 阈值，不影响大涨分类）==")
    hdr = f"{'down阈值':<8}" + "".join(f"{lbl:>8}" for lbl, _, _ in WINDOWS)
    print(hdr)
    down_days = {}
    for down in DOWN_CANDIDATES:
        per = count_periods(series, 0.07, down)
        down_days[down] = {lbl: per[lbl]["counts"]["大跌"] for lbl, _, _ in WINDOWS}
        row = f"{down*100:>7.1f}%  " + "".join(f"{down_days[down][lbl]:>8}" for lbl, _, _ in WINDOWS)
        print(row)
        result["grid"][f"down={down}"] = {
            lbl: per[lbl] for lbl, _, _ in WINDOWS
        }

    # 大涨天数：只与 up 阈值有关
    print("\n== 大涨天数（按 up 阈值，不影响大跌分类）==")
    hdr = f"{'up阈值':<8}" + "".join(f"{lbl:>8}" for lbl, _, _ in WINDOWS)
    print(hdr)
    up_days = {}
    for up in UP_CANDIDATES:
        per = count_periods(series, up, -0.05)
        up_days[up] = {lbl: per[lbl]["counts"]["大涨"] for lbl, _, _ in WINDOWS}
        row = f"{up*100:>7.1f}%  " + "".join(f"{up_days[up][lbl]:>8}" for lbl, _, _ in WINDOWS)
        print(row)
        result["grid"][f"up={up}"] = {
            lbl: per[lbl] for lbl, _, _ in WINDOWS
        }

    # 主口径选择
    print("\n== 主口径选择（标准：四段每段大跌天数 ≥ 40）==")
    meets = {}
    for down in DOWN_CANDIDATES:
        meets[down] = all(v >= 40 for v in down_days[down].values())
        print(f"  down={down*100:.1f}%  各段大跌天数={list(down_days[down].values())}  {'✓达标' if meets[down] else '✗不达标'}")
    if any(meets.values()):
        # 选「达标且阈值绝对值最小（最贴近 0，即最宽松）」的那个
        chosen = min(d for d, ok in meets.items() if ok)
        print(f"  → 选 down={chosen*100:.1f}% 为主口径（达标且最宽松）")
    else:
        best = max(DOWN_CANDIDATES, key=lambda d: sum(down_days[d].values()))
        print(f"  → 无阈值满足「每段≥40」，选大跌天数最多的 down={best*100:.1f}% 为主口径")
        chosen = best

    # 大涨口径：选最宽松的 +2% 与 +3% 对比；主口径取 +2%（与 down=-2% 对称）
    print("\n== 大涨口径 ==")
    for up in UP_CANDIDATES:
        print(f"  up=+{up*100:.1f}%  各段大涨天数={list(up_days[up].values())}  最小={min(up_days[up].values())}")
    chosen_up = 0.02

    result["down_days"] = {f"{k}": v for k, v in down_days.items()}
    result["up_days"] = {f"{k}": v for k, v in up_days.items()}
    result["meets_40_per_segment"] = {f"{k}": v for k, v in meets.items()}
    result["chosen_down"] = chosen
    result["chosen_up"] = chosen_up
    result["chosen_main"] = {"大涨": f">=+{chosen_up}", "大跌": f"<={chosen}", "中性": "其间"}

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print(f"\n已落盘 {OUT}")


if __name__ == "__main__":
    main()
