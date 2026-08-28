"""旧脚本参考实现：偷涨型（水下二次金叉）核心逻辑（仅用于一致性测试）。

从 `~/.openclaw/workspace/tools/daily_stock_picker.py::detect_underwater_double_golden`
和 `stealth_rally_scanner.py` 的最近水下金叉查找逻辑原样抽取。

注意：旧脚本 `has_recent_limit_up` 用成交额 amount 当昨收（bug），
一致性测试只比对「水下二次金叉 + 金叉天数」这段确定性逻辑，涨停过滤的
bug 修复单独记录在 docs/策略迁移说明.md。请勿在业务代码 import 本模块。
"""

from __future__ import annotations

from typing import Sequence


def legacy_calc_macd(closes: Sequence[float]):
    """旧脚本 daily_stock_picker.py::calc_macd（n<33 返回全 0）。"""
    n = len(closes)
    if n < 33:
        return [0] * n, [0] * n, [0] * n
    ema12 = _legacy_calc_ema(closes, 12)
    ema26 = _legacy_calc_ema(closes, 26)
    dif = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
    dea = _legacy_calc_ema(dif, 9)
    macd_bar = [(d - e) * 2 for d, e in zip(dif, dea)]
    return dif, dea, macd_bar


def _legacy_calc_ema(data: Sequence[float], period: int) -> list[float]:
    """旧脚本 calc_ema（首值做种子）。"""
    if len(data) < 2:
        return [data[0]] * len(data)
    k = 2 / (period + 1)
    result = [data[0]]
    for i in range(1, len(data)):
        result.append(data[i] * k + result[-1] * (1 - k))
    return result


def legacy_detect_underwater_double_golden(dif, dea, bar):
    """旧脚本 daily_stock_picker.py::detect_underwater_double_golden 逐行复刻。"""
    n = len(bar)
    if n < 40:
        return 0, ""

    cross_idxs = []
    for i in range(n - 2, 5, -1):
        if dif[i] <= dea[i] and dif[i + 1] > dea[i + 1]:
            if dif[i + 1] < 0 and dea[i + 1] < 0:
                cross_idxs.append(i + 1)

    if len(cross_idxs) < 2:
        return 0, ""

    second_cross = cross_idxs[0]
    first_cross = cross_idxs[1]

    if second_cross - first_cross < 5:
        return 0, ""

    bars_after = bar[second_cross:]
    if len(bars_after) < 3:
        return 0, ""

    red_streak = 0
    for b in reversed(bars_after):
        if b > 0:
            red_streak += 1
        else:
            break
    if red_streak < 2:
        return 0, ""

    if bars_after[-1] <= 0 or bars_after[-1] <= bars_after[-2]:
        return 0, ""

    base_score = 13
    detail = "水下二次金叉+红柱确认(偷涨型)"

    mid = (first_cross + second_cross) // 2
    bars_s1 = [bar[i] for i in range(first_cross, mid) if bar[i] < 0]
    bars_s2 = [bar[i] for i in range(mid, second_cross) if bar[i] < 0]

    if bars_s1 and bars_s2 and min(bars_s2) > min(bars_s1):
        base_score += 5
        detail += "+底背离"

    return base_score, detail


def legacy_find_last_uw_cross(dif, dea):
    """旧脚本 stealth_rally_scanner.py 的最近水下金叉索引查找。"""
    n = len(dif)
    for i in range(n - 2, 5, -1):
        if dif[i] <= dea[i] and dif[i + 1] > dea[i + 1]:
            if dif[i + 1] < 0 and dea[i + 1] < 0:
                return i + 1
    return None
