#!/usr/bin/env python3
"""从 hsjday 实际交易日反推 A股节假日表，生成 ``packages/market/market/holidays.py``。

背景（阶段 4，见 docs/回测迁移说明.md）：
    阶段 1 的 ``market.calendar.is_trading_day`` 是「工作日=交易日」的简化版，
    没排除春节/国庆等长假休市。回测的持有期计算依赖交易日，必须做对。

推荐做法（任务书原文）：从 hsjday 实际存在的交易日反推日历，比硬编码节假日表
更可靠——任何 A股真正的休市日（法定节假日、临时休市）都不会出现在数据里。

原理：
    A股个股/ETF 在任意真正的交易日，市场上至少有一只标的会有日线数据。
    因此「所有 .day 文件里出现过的日期集合」就是完整的 A股交易日集合。
    反过来，「2020-01-01 ~ 数据末日」之间的工作日若不在该集合里，就是休市日。

用法（仓库根目录，只读 hsjday，不改任何数据）：

    .venv/bin/python scripts/make_trading_calendar.py \
        --hsjday ~/Desktop/每日复盘/hsjday \
        --out packages/market/market/holidays.py

输出模块内容为静态 frozenset，供 ``market.calendar`` 在运行期 O(1) 查询，
不依赖数据目录、不重复扫描文件。
"""

from __future__ import annotations

import argparse
import struct
from datetime import date, datetime, timedelta
from pathlib import Path

# .day 记录格式：首字段是 YYYYMMDD 整数
_ST = struct.Struct("<I")

# 覆盖范围起点（阶段要求至少覆盖 2020-2026）
RANGE_START = date(2020, 1, 1)

_MODULE_HEADER = '''"""A股法定休市日（节假日）静态表。

由 ``scripts/make_trading_calendar.py`` 从 hsjday 实际交易日反推生成：
「数据末日之前的工作日」若在任何 .day 文件里都没出现过，即为休市日。
覆盖范围 2020-01-01 起；数据末日之后的日期不在此表内，``is_trading_day``
对它们回退到「工作日=交易日」的近似（未来节假日未知，属于合理降级）。

本文件是数据文件，请勿手改；数据更新后用上面的脚本重新生成。
"""

from __future__ import annotations

from datetime import date

# 休市日（YYYY-MM-DD，已按升序）
_HOLIDAY_STRS: tuple[str, ...] = (
'''


def collect_trading_days(hsjday_root: Path) -> set[date]:
    """扫描 hsjday 全部 .day 文件，返回出现过日期的集合。"""
    days: set[date] = set()
    files = 0
    for market in ("sh", "sz", "bj"):
        lday = hsjday_root / market / "lday"
        if not lday.is_dir():
            continue
        for fn in lday.iterdir():
            if not fn.name.endswith(".day"):
                continue
            files += 1
            data = fn.read_bytes()
            for off in range(0, len(data) - 32 + 1, 32):
                (date_int,) = _ST.unpack_from(data, off)
                try:
                    days.add(datetime.strptime(str(date_int), "%Y%m%d").date())
                except ValueError:
                    continue
    print(f"扫描 {files} 个 .day 文件，共 {len(days)} 个不同交易日")
    return days


def derive_holidays(days: set[date]) -> list[date]:
    """由交易日集合反推休市日（仅覆盖到数据末日为止）。"""
    max_day = max(days)
    holidays: list[date] = []
    d = RANGE_START
    while d <= max_day:
        if d.weekday() < 5 and d not in days:
            holidays.append(d)
        d += timedelta(days=1)
    return holidays


def render_module(holidays: list[date]) -> str:
    """把休市日列表渲染成 holidays.py 源码。"""
    lines = [f'    "{d.isoformat()}",' for d in holidays]
    body = "\n".join(lines)
    tail = f''')

# 运行期查询用 frozenset（date 对象）
HOLIDAYS: frozenset[date] = frozenset(
    date.fromisoformat(s) for s in _HOLIDAY_STRS
)
'''
    return _MODULE_HEADER + body + tail


def main() -> None:
    parser = argparse.ArgumentParser(description="从 hsjday 反推 A股节假日表")
    parser.add_argument("--hsjday", required=True, help="hsjday 根目录")
    parser.add_argument("--out", required=True, help="输出 holidays.py 路径")
    args = parser.parse_args()

    days = collect_trading_days(Path(args.hsjday).expanduser())
    holidays = derive_holidays(days)
    print(f"休市日（工作日但无数据）: {len(holidays)} 天，"
          f"截至 {max(days).isoformat()}")

    out = Path(args.out)
    out.write_text(render_module(holidays), encoding="utf-8")
    print(f"已写入 {out}")


if __name__ == "__main__":
    main()
