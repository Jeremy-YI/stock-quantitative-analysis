#!/usr/bin/env python3
"""阶段 11：regime 时间序列（regime 决定选股池，比 market/regime.py 高一层）。

按指数 20 日涨跌幅给每个交易日打 regime 标签：
    r20 >= +5%  → 大涨
    r20 <= -5%  → 大跌
    其余        → 中性

数据源：本地通达信指数日线（上证 sh000001）。
四段区间沿用阶段 9/10（与 scripts/run_oos_factors.py 一致）：
    IS     2026-03-01 ~ 2026-08-27
    OOS-A  2023-01-01 ~ 2023-12-31
    OOS-B  2024-01-01 ~ 2024-12-31
    OOS-C  2025-01-01 ~ 2026-02-28

落盘 data/regime_timeline.json（逐日 date / r20 / regime），并打印四段占比。

用法（仓库根目录）：
    .venv/bin/python scripts/run_regime_timeline.py
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

# regime 阈值（按任务书：≥+5% 大涨 / ≤-5% 大跌 / 其间中性）
R20_UP = 0.05
R20_DOWN = -0.05
LOOKBACK_DAYS = 20

WINDOWS: list[tuple[str, str, str]] = [
    ("IS", "2026-03-01", "2026-08-27"),
    ("OOS-A", "2023-01-01", "2023-12-31"),
    ("OOS-B", "2024-01-01", "2024-12-31"),
    ("OOS-C", "2025-01-01", "2026-02-28"),
]

OUT = ROOT / "data" / "regime_timeline.json"


def classify(r20: float) -> str:
    if r20 >= R20_UP:
        return "大涨"
    if r20 <= R20_DOWN:
        return "大跌"
    return "中性"


def main() -> None:
    idx_path = DEFAULT_HSJDAY_ROOT / "sh" / "lday" / "sh000001.day"
    if not idx_path.exists():
        print(f"[FATAL] 上证指数日线不存在：{idx_path}", file=sys.stderr)
        sys.exit(1)

    df = parse_day_file(idx_path).set_index("date")
    close = df["close"]
    r20 = close.pct_change(LOOKBACK_DAYS)
    series = pd.DataFrame({"close": close, "r20": r20}).dropna(subset=["r20"])
    series["regime"] = series["r20"].map(classify)

    # 输出窗口：覆盖四段，额外往前留 20 个交易日供 r20 计算（2022-12-01 起）。
    out_start = date(2022, 12, 1)
    out_end = date(2026, 8, 27)
    sub = series.loc[out_start:out_end]

    days = [
        {
            "date": d.isoformat(),
            "r20": round(float(row["r20"]), 6),
            "regime": row["regime"],
        }
        for d, row in sub.iterrows()
    ]

    periods: dict[str, dict] = {}
    print(f"{'区间':<7} {'总交易日':>7} {'大涨':>6} {'中性':>6} {'大跌':>6} | 占比(大涨/中性/大跌)")
    for label, start, end in WINDOWS:
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
        seg = sub.loc[s:e]
        counts = seg["regime"].value_counts().to_dict()
        n = len(seg)
        up = counts.get("大涨", 0)
        mid = counts.get("中性", 0)
        down = counts.get("大跌", 0)
        periods[label] = {
            "start": start,
            "end": end,
            "days": n,
            "counts": {"大涨": up, "中性": mid, "大跌": down},
            "pct": {
                "大涨": round(up / n, 4) if n else None,
                "中性": round(mid / n, 4) if n else None,
                "大跌": round(down / n, 4) if n else None,
            },
        }
        print(
            f"{label:<7} {n:>7} {up:>6} {mid:>6} {down:>6} | "
            f"{up/n*100 if n else 0:5.1f}% / {mid/n*100 if n else 0:5.1f}% / {down/n*100 if n else 0:5.1f}%"
        )

    payload = {
        "index": "sh000001",
        "lookback_days": LOOKBACK_DAYS,
        "thresholds": {"大涨": f">={R20_UP}", "大跌": f"<={R20_DOWN}", "中性": "其间"},
        "periods": periods,
        "days": days,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\n已落盘 {OUT}（{len(days)} 个交易日）")


if __name__ == "__main__":
    main()
