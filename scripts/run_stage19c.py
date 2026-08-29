#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 19c：Jeremy 真实切换策略全周期回测（2020-2026）。

Jeremy 口述的半导体买卖日期（卖后切换红利低波），用等权篮子回测：
- 成长篮子：半导体成分（sector_stocks.json，178 只）
- 防守篮子：中证红利低波动 H30269（50 只）
- 对照：一直持半导体 / 一直持红利低波
输出：累积收益、年化、最大回撤、每笔交易收益、分年收益。
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datasource.tdx.reader import resolve_hsjday_root
from scripts.run_stage19b import basket_daily

# Jeremy 的半导体买卖日期（买→卖，卖后红利低波）
TRADES = [
    ("2020-10-29", "2021-01-26"),
    ("2021-04-19", "2021-09-16"),
    ("2022-03-16", "2022-03-24"),
    ("2022-04-27", "2022-07-11"),
    ("2022-10-12", "2022-11-23"),
    ("2023-01-05", "2023-02-23"),
    ("2023-03-21", "2023-05-11"),
    ("2023-06-13", "2023-06-21"),
    ("2023-07-31", "2023-08-09"),
    ("2023-10-27", "2023-11-24"),
    ("2024-02-06", "2024-03-25"),
    ("2024-04-26", "2024-05-15"),
    ("2024-09-24", "2024-11-14"),
    ("2025-02-06", "2025-02-28"),
    ("2025-04-09", "2025-04-16"),
    ("2025-06-24", "2025-09-03"),
    ("2025-12-30", "2026-02-02"),
    ("2026-03-02", "2026-03-13"),
    ("2026-04-28", "2026-05-21"),
    ("2026-06-15", "2026-07-02"),
]
START = date(2020, 10, 29)
END = date(2026, 8, 28)


def main() -> None:
    root = resolve_hsjday_root()
    sec = json.loads(Path("/Users/yanhongyi/Documents/Obsidian Vault/大富翁/A股/A持仓-复盘/A每日复盘/板块资金流向/sector_stocks.json").read_text())
    semi_codes = sorted(sec["半导体"]["stocks"])
    idx = json.loads((ROOT / "data" / "stage18_index_universes.json").read_text())
    div_codes = sorted(idx["H30269"]["stocks"])

    semi_r = basket_daily(semi_codes, root)
    div_r = basket_daily(div_codes, root)

    # 交易日历（取两篮子 + 区间的并集）
    cal = sorted(set(semi_r.index) & set(div_r.index) & {d for d in semi_r.index if START <= d <= END})

    # 建 regime 掩码：半导体=True
    regime = np.zeros(len(cal), dtype=bool)
    for bs, ss in TRADES:
        b, s = date.fromisoformat(bs), date.fromisoformat(ss)
        for j, d in enumerate(cal):
            if b <= d <= s:
                regime[j] = True

    sr = semi_r.reindex(cal).fillna(0).to_numpy()
    dr = div_r.reindex(cal).fillna(0).to_numpy()
    strat = np.where(regime, sr, dr)

    def cum(r):
        return float(np.prod(1.0 + r) - 1.0)
    def dd(r):
        eq = np.cumprod(1.0 + r)
        return float(np.min(eq / np.maximum.accumulate(eq) - 1.0))
    def ann(r, n):
        return float((1.0 + cum(r)) ** (252.0 / n) - 1.0)
    def sharpe(r):
        return float(np.mean(r) / (np.std(r) + 1e-12) * np.sqrt(252))

    n = len(cal)
    years = np.array([d.year for d in cal])

    # 每笔交易收益
    trades = []
    for bs, ss in TRADES:
        b, s = date.fromisoformat(bs), date.fromisoformat(ss)
        seg = sr[np.array([b <= d <= s for d in cal])]
        r = cum(seg) if len(seg) else 0.0
        days = int(len(seg))
        trades.append({"buy": bs, "sell": ss, "days": days, "ret": round(r * 100, 2)})

    # 分年收益（策略）
    yearly = {}
    for y in sorted(set(years)):
        m = years == y
        yearly[str(y)] = round(cum(strat[m]) * 100, 2)

    out = {
        "period": [str(START), str(END)],
        "n_days": n,
        "n_trades": len(TRADES),
        "time_in_semi": round(float(regime.mean()), 3),
        "cumulative": {
            "switch": round(cum(strat) * 100, 2),
            "always_semi": round(cum(sr) * 100, 2),
            "always_div": round(cum(dr) * 100, 2),
        },
        "annualized": {
            "switch": round(ann(strat, n) * 100, 2),
            "always_semi": round(ann(sr, n) * 100, 2),
            "always_div": round(ann(dr, n) * 100, 2),
        },
        "max_drawdown": {
            "switch": round(dd(strat) * 100, 2),
            "always_semi": round(dd(sr) * 100, 2),
            "always_div": round(dd(dr) * 100, 2),
        },
        "sharpe": {
            "switch": round(sharpe(strat), 2),
            "always_semi": round(sharpe(sr), 2),
            "always_div": round(sharpe(dr), 2),
        },
        "trades": trades,
        "yearly_switch": yearly,
    }

    (ROOT / "data" / "stage19c_results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print("=== 全周期 2020/10/29 ~ 2026/08/28（等权，前复权）===")
    print("累计收益：切换 %+.1f%% | 一直半导体 %+.1f%% | 一直红利低波 %+.1f%%" %
          (out["cumulative"]["switch"], out["cumulative"]["always_semi"], out["cumulative"]["always_div"]))
    print("年化：    切换 %+.1f%% | 一直半导体 %+.1f%% | 一直红利低波 %+.1f%%" %
          (out["annualized"]["switch"], out["annualized"]["always_semi"], out["annualized"]["always_div"]))
    print("最大回撤：切换 %+.1f%% | 一直半导体 %+.1f%% | 一直红利低波 %+.1f%%" %
          (out["max_drawdown"]["switch"], out["max_drawdown"]["always_semi"], out["max_drawdown"]["always_div"]))
    print("夏普：    切换 %.2f | 一直半导体 %.2f | 一直红利低波 %.2f" %
          (out["sharpe"]["switch"], out["sharpe"]["always_semi"], out["sharpe"]["always_div"]))
    print("在半导体时间占比 %.0f%%" % (out["time_in_semi"] * 100))
    print()
    print("=== 每笔半导体交易 ===")
    win = 0
    for t in trades:
        if t["ret"] > 0:
            win += 1
        print("  %s → %s (%3d天) : %+.1f%%" % (t["buy"], t["sell"], t["days"], t["ret"]))
    print("  胜率 %d/%d" % (win, len(trades)))
    print()
    print("=== 分年收益（切换策略）===")
    for y, r in yearly.items():
        print("  %s : %+.1f%%" % (y, r))


if __name__ == "__main__":
    main()
