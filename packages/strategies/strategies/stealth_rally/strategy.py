"""偷涨型策略：MACD 水下二次金叉 + 红柱确认 + 近10日无涨停。

复刻 `stealth_rally_scanner.py` 的核心逻辑（`detect_underwater_double_golden`），
与每日 TOP5（追涨停型）互补——这是埋伏型，找正在偷涨、尚未被市场注意的票。

唯一有意差异：旧脚本 `has_recent_limit_up` 用成交额 amount 当昨收（bug），
本实现用真实昨收，详见 docs/策略迁移说明.md。
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from indicators.macd import calc_macd
from strategies.filters import SymbolKind
from strategies.signal import Signal
from strategies.stealth_rally.config import StealthRallyConfig, default_config

NAME = "stealth_rally"
DESCRIPTION = "MACD 水下二次金叉 + 红柱确认 + 近10日无涨停（偷涨型）"
SIGNAL_TYPE = "stealth_rally"
TARGET_KINDS = (SymbolKind.STOCK,)


def detect_underwater_double_golden(
    dif: list[float], dea: list[float], bar: list[float]
) -> tuple[int, str]:
    """检测 MACD 零轴以下二次金叉 + 红柱确认（底背离为加分项）。

    与旧脚本 `daily_stock_picker.py::detect_underwater_double_golden` 逐行一致。
    返回 (加分, 描述)；不满足返回 (0, "")。
    """
    n = len(bar)
    if n < 40:
        return 0, ""

    # 1. 收集水下金叉位置
    cross_idxs: list[int] = []
    for i in range(n - 2, 5, -1):
        if dif[i] <= dea[i] and dif[i + 1] > dea[i + 1]:
            if dif[i + 1] < 0 and dea[i + 1] < 0:
                cross_idxs.append(i + 1)

    if len(cross_idxs) < 2:
        return 0, ""

    second_cross = cross_idxs[0]  # 最近
    first_cross = cross_idxs[1]  # 上次

    if second_cross - first_cross < 5:
        return 0, ""

    # 2. 核心：第二金叉后红柱确认（绿柱走完 + 红柱持续）
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

    # 红柱在放大
    if bars_after[-1] <= 0 or bars_after[-1] <= bars_after[-2]:
        return 0, ""

    base_score = 13
    detail = "水下二次金叉+红柱确认(偷涨型)"

    # 3. 加分：绿柱底背离
    mid = (first_cross + second_cross) // 2
    bars_s1 = [bar[i] for i in range(first_cross, mid) if bar[i] < 0]
    bars_s2 = [bar[i] for i in range(mid, second_cross) if bar[i] < 0]

    if bars_s1 and bars_s2 and min(bars_s2) > min(bars_s1):
        base_score += 5
        detail += "+底背离"

    return base_score, detail


def scan(
    candles: dict[str, pd.DataFrame],
    as_of: date,
    config: StealthRallyConfig | None = None,
) -> list[Signal]:
    """对一批日线扫描偷涨型信号。"""
    cfg = config or default_config()
    signals: list[Signal] = []

    for symbol in sorted(candles):
        df = candles[symbol]
        signal = _evaluate(symbol, df, as_of, cfg)
        if signal is not None:
            signals.append(signal)

    return signals


def _evaluate(
    symbol: str, df: pd.DataFrame, as_of: date, cfg: StealthRallyConfig
) -> Signal | None:
    """对单只标的判定偷涨型。不满足条件返回 None。"""
    if df is None or len(df) < cfg.min_bars:
        return None

    closes = df["close"].astype(float).tolist()
    volumes = df["volume"].astype(float).tolist()
    n = len(closes)

    dif, dea, bar = calc_macd(closes)

    bonus, detail = detect_underwater_double_golden(dif, dea, bar)
    if bonus == 0:
        return None

    # 找最近一次水下金叉的索引
    last_uw_cross_idx = None
    for i in range(n - 2, 5, -1):
        if dif[i] <= dea[i] and dif[i + 1] > dea[i + 1]:
            if dif[i + 1] < 0 and dea[i + 1] < 0:
                last_uw_cross_idx = i + 1
                break
    if last_uw_cross_idx is None:
        return None

    cross_days_ago = n - 1 - last_uw_cross_idx
    if cross_days_ago > cfg.max_cross_age:
        return None

    # 最近是否有涨停（修正版：用真实昨收，不用 amount）
    if _has_recent_limit_up(closes, cfg.limit_up_lookback, cfg.limit_up_pct):
        return None

    score = _score(closes, volumes, dif, dea, bar, last_uw_cross_idx, cross_days_ago, bonus)

    price_at_cross = closes[last_uw_cross_idx]
    price_now = closes[-1]
    stealth_gain = (price_now - price_at_cross) / price_at_cross * 100.0

    avol20 = sum(volumes[-21:-1]) / 20.0 if len(volumes) >= 21 else volumes[-1]
    vol_ratio = volumes[-1] / avol20 if avol20 > 0 else 1.0

    return Signal(
        symbol=symbol,
        strategy=NAME,
        signal_type=SIGNAL_TYPE,
        score=round(score, 1),
        triggered_at=as_of,
        metrics={
            "cross_days": cross_days_ago,
            "stealth_gain": round(stealth_gain, 2),
            "dif_now": round(float(dif[-1]), 4),
            "dif_cross": round(float(dif[last_uw_cross_idx]), 4),
            "bar_now": round(float(bar[-1]), 4),
            "vol_ratio": round(vol_ratio, 2),
            "close": round(price_now, 2),
            "detail": detail,
        },
    )


def _has_recent_limit_up(closes: list[float], lookback: int, pct_threshold: float) -> bool:
    """检查最近 ``lookback`` 日内是否有涨停（修正版：用真实昨收）。"""
    for i in range(max(1, len(closes) - lookback), len(closes)):
        prev_close = closes[i - 1]
        if prev_close <= 0:
            continue
        chg_pct = (closes[i] - prev_close) / prev_close * 100.0
        if chg_pct >= pct_threshold:
            return True
    return False


def _score(
    closes: list[float],
    volumes: list[float],
    dif: list[float],
    dea: list[float],
    bar: list[float],
    cross_idx: int,
    cross_days_ago: int,
    bonus: int,
) -> float:
    """复刻旧脚本的打分逻辑（纯函数，方便单测）。"""
    score = float(bonus)

    # DIF 趋势强度：当前 DIF - 金叉时 DIF，最多 +5
    dif_gain = dif[-1] - dif[cross_idx]
    score += min(dif_gain * 10.0, 5.0)

    # 红柱强度：当前 bar 值，最多 +5
    score += min(float(bar[-1]) * 5.0, 5.0)

    # 金叉天数（越近越好）
    if cross_days_ago <= 5:
        score += 5
    elif cross_days_ago <= 10:
        score += 3
    elif cross_days_ago <= 20:
        score += 2

    # 偷涨幅度（适中最佳）
    price_at_cross = closes[cross_idx]
    price_now = closes[-1]
    stealth_gain = (price_now - price_at_cross) / price_at_cross * 100.0 if price_at_cross else 0.0
    if 5 <= stealth_gain <= 30:
        score += 3
    elif stealth_gain > 30:
        score -= 2

    # 当前状态：MACD 是否已回到水上
    if dif[-1] > 0:
        score += 3

    # 最近 5 日趋势：持续小阳线
    recent_closes = closes[-5:]
    up_days = sum(1 for i in range(1, len(recent_closes)) if recent_closes[i] > recent_closes[i - 1])
    score += up_days

    # 量价：温和放量或缩量
    avol20 = sum(volumes[-21:-1]) / 20.0 if len(volumes) >= 21 else volumes[-1]
    vol_ratio = volumes[-1] / avol20 if avol20 > 0 else 1.0
    if 0.5 <= vol_ratio <= 1.2:
        score += 2

    return score
