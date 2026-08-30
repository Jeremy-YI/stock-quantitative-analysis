"""B1 / B2 / B3 信号策略。

三种信号（判定逻辑集中在 ``_evaluate``，阈值全部来自 ``B1B2B3Config``）：

    B1 = 超卖：J < j_b1_threshold 或 K ≤ k_b1_threshold
    B2 = 右侧确认：PCT ≥ 3.7% + 放量（量比 > 1.2）+ 阳线 + J 上行（J > 昨日 J）
    B3 = 缩量洗盘中继：量比 < 0.8 + 5 日振幅 < 8%

三信号相互独立，同一标的可同时触发多个 signal_type。
统一接口 ``scan(candles, as_of, config) -> list[Signal]``。
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from indicators.kdj import calc_kdj
from indicators.volume import calc_volume_ratio
from strategies.b1b2b3.config import B1B2B3Config, default_config
from strategies.filters import SymbolKind
from strategies.signal import Signal

NAME = "b1b2b3"
LABEL = "超卖反弹"
DESCRIPTION = "B1 超卖 / B2 右侧确认 / B3 缩量洗盘中继（KDJ + 量价）"
TARGET_KINDS = (SymbolKind.STOCK,)

# 信号子类型与打分（供看板排序，右侧确认最强、超卖次之、洗盘中继最弱）
SCORE = {"b1": 70.0, "b2": 85.0, "b3": 55.0}


def scan(
    candles: dict[str, pd.DataFrame],
    as_of: date,
    config: B1B2B3Config | None = None,
) -> list[Signal]:
    """对一批日线扫描 B1/B2/B3 信号。

    Args:
        candles: {symbol: 日线 DataFrame}，列需含 date/open/high/low/close/volume。
        as_of: 扫描日（写入 Signal.triggered_at）。
        config: 阈值配置，缺省用 default_config()。

    Returns:
        命中的 Signal 列表（按 symbol 升序稳定排序）。
    """
    cfg = config or default_config()
    signals: list[Signal] = []

    for symbol in sorted(candles):
        df = candles[symbol]
        signals.extend(_evaluate(symbol, df, as_of, cfg))

    return signals


def _evaluate(
    symbol: str, df: pd.DataFrame, as_of: date, cfg: B1B2B3Config
) -> list[Signal]:
    """对单只标的判定三信号。数据不足返回空列表。"""
    if df is None or len(df) < cfg.min_bars:
        return []

    closes = df["close"].astype(float).tolist()
    highs = df["high"].astype(float).tolist()
    lows = df["low"].astype(float).tolist()
    volumes = df["volume"].astype(float).tolist()

    k_vals, d_vals, j_vals = calc_kdj(highs, lows, closes)

    close_now = closes[-1]
    close_prev = closes[-2] if len(closes) >= 2 else close_now
    j_now = j_vals[-1]
    j_prev = j_vals[-2] if len(j_vals) >= 2 else j_now
    k_now = k_vals[-1]
    d_now = d_vals[-1]

    pct = (close_now - close_prev) / close_prev * 100.0 if close_prev else 0.0
    volume_ratio = calc_volume_ratio(volumes)[-1]
    range_5d = (
        (max(highs[-5:]) - min(lows[-5:])) / close_now * 100.0 if close_now else 0.0
    )

    out: list[Signal] = []

    # B1 超卖：J < 16 或 K ≤ 30
    if j_now < cfg.j_b1_threshold or k_now <= cfg.k_b1_threshold:
        out.append(
            Signal(
                symbol=symbol,
                strategy=NAME,
                signal_type="b1",
                score=SCORE["b1"],
                triggered_at=as_of,
                metrics={
                    "j": round(j_now, 4),
                    "k": round(k_now, 4),
                    "d": round(d_now, 4),
                    "close": round(close_now, 4),
                    "pct": round(pct, 4),
                    "volume_ratio": round(volume_ratio, 4),
                },
            )
        )

    # B2 右侧确认：PCT≥3.7 + 放量 + 阳线 + J 上行
    is_yang = close_now > close_prev
    is_fangliang = volume_ratio > cfg.volume_ratio_b2_threshold
    is_j_up = j_now > j_prev
    if pct >= cfg.pct_b2_threshold and is_yang and is_fangliang and is_j_up:
        out.append(
            Signal(
                symbol=symbol,
                strategy=NAME,
                signal_type="b2",
                score=SCORE["b2"],
                triggered_at=as_of,
                metrics={
                    "pct": round(pct, 4),
                    "volume_ratio": round(volume_ratio, 4),
                    "j": round(j_now, 4),
                    "j_prev": round(j_prev, 4),
                    "close": round(close_now, 4),
                },
            )
        )

    # B3 缩量洗盘中继：量比 < 0.8 + 5 日振幅 < 8%
    if volume_ratio < cfg.volume_ratio_b3_threshold and range_5d < cfg.range_b3_threshold:
        out.append(
            Signal(
                symbol=symbol,
                strategy=NAME,
                signal_type="b3",
                score=SCORE["b3"],
                triggered_at=as_of,
                metrics={
                    "volume_ratio": round(volume_ratio, 4),
                    "range_5d": round(range_5d, 4),
                    "close": round(close_now, 4),
                },
            )
        )

    return out
