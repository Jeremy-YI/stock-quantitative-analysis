"""复权处理。

背景（阶段 1 遗留，阶段 9 接入）：通达信 hsjday .day 文件为**不复权**原始数据，
除权除息日会在 K 线上留下「假跌幅」（除权缺口），回测若不处理会把除权当成真实
暴跌、把除权后的连续 K 线算成假收益。本模块提供两类能力：

    1. 启发式除权检测（``detect_ex_rights``）：从原始数据自推（无需外部复权因子）。
    2. 前/后复权换算（``forward_adjust_frame`` / ``backward_adjust_frame``）。

复权口径说明：

    - **前复权**（DEFAULT_ADJUST_MODE）：把历史价格整体缩放，使最新价为真实价、
      历史价格连续（除权日不再有缺口）。回测统一用前复权口径。
    - **后复权**：把最新价连同历史一起缩放，使「累计收益」等于「总回报」（含分红
      再投）。仅用于算绝对收益，不用于 K 线形态。
    - 精确的复权因子需外部数据（AKShare 前复权接口 / 除权除息表）；本模块的
      ``detect_ex_rights`` 是「现有数据推算」的启发式：**只识别除权缺口超过涨跌停
      幅度的「大除权」**（送转股 / 高分红），小分红导致的缺口识别不到。接入精确
      因子列为后续 TODO（见 docs/样本外验证报告.md 遗留项）。

启发式除权检测原理：主板（60/00）涨跌停 ±10%、创业板/科创板（30/68）±20%，
当日收益若**超过跌停幅度**（如主板 < -10.5%、创业板 < -20.5%）不可能是跌停，
只能来自除权除息（或数据错误）。据此把「超过跌停幅度的假跌幅」判定为除权日。
"""

from __future__ import annotations

from enum import Enum

import numpy as np
import pandas as pd


class AdjustMode(str, Enum):
    """复权模式枚举。"""

    FORWARD = "forward"  # 前复权
    BACKWARD = "backward"  # 后复权
    NONE = "none"  # 不复权


DEFAULT_ADJUST_MODE = AdjustMode.FORWARD

# 各板块的跌停幅度（用于启发式除权检测；留 0.5pp 余量避免把「跌停+滑点」误判）
_BOARD_LIMIT_DOWN = {
    ("60", "00"): -0.105,  # 主板 ±10%
    ("30", "68"): -0.205,  # 创业板/科创板 ±20%
    ("43", "83", "87", "88", "92"): -0.305,  # 北交所 ±30%
}


def limit_down_pct(symbol: str) -> float:
    """按代码前缀返回跌停幅度（负值，留余量），未知归主板 -10.5%。"""
    for prefixes, limit in _BOARD_LIMIT_DOWN.items():
        if symbol.startswith(prefixes):
            return limit
    return -0.105


def detect_ex_rights(closes: np.ndarray | list[float], limit_down: float) -> np.ndarray:
    """检测除权日：当日收益 < limit_down（超过跌停幅度的假跌幅）记为 True。

    Args:
        closes: 原始收盘价序列（升序）。
        limit_down: 跌停幅度（负值，如主板 -0.105）。

    Returns:
        与 closes 等长的布尔数组，True = 该日疑似除权（closes[0] 恒为 False）。
    """
    c = np.asarray(closes, dtype=float)
    n = len(c)
    out = np.zeros(n, dtype=bool)
    for i in range(1, n):
        if c[i - 1] > 0 and c[i] > 0 and (c[i] / c[i - 1] - 1.0) < limit_down:
            out[i] = True
    return out


def forward_adjust_closes(closes: np.ndarray | list[float], ex_rights: np.ndarray) -> np.ndarray:
    """前复权收盘价：除权日「假跌幅」被抹平（除权日复权收益 ≈ 0）。

    实现：从最新价向前回推累积复权因子。对除权日 i，其前一日及更早的价格统一乘以
    close[i]/close[i-1]（= 1+原始收益），使除权日的复权收益回到 0。
    """
    c = np.asarray(closes, dtype=float).copy()
    n = len(c)
    ex = np.asarray(ex_rights, dtype=bool)
    factor = np.ones(n, dtype=float)
    for i in range(n - 1, 0, -1):
        factor[i - 1] = factor[i]
        if ex[i] and c[i - 1] > 0:
            factor[i - 1] *= c[i] / c[i - 1]
    return c * factor


def forward_adjust_frame(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """对单只标的日线做前复权（OHLC 同缩放，成交额/成交量不变）。

    Args:
        df: 含 date/open/high/low/close/volume/amount 列的日线 DataFrame。
        symbol: 6 位代码（用于按板块定跌停幅度）。

    Returns:
        新 DataFrame，OHLC 列已前复权，其余列不变（成交量/成交额不复权）。
    """
    if df is None or df.empty:
        return df
    out = df.copy()
    closes = pd.to_numeric(out["close"], errors="coerce").to_numpy(dtype=float)
    ex = detect_ex_rights(closes, limit_down_pct(symbol))
    adj = forward_adjust_closes(closes, ex)
    ratio = adj / np.where(closes > 0, closes, np.nan)
    ratio = np.where(np.isfinite(ratio), ratio, 1.0)
    for col in ("open", "high", "low", "close"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").to_numpy(dtype=float) * ratio
    return out


def backward_adjust_closes(closes: np.ndarray | list[float], ex_rights: np.ndarray) -> np.ndarray:
    """后复权收盘价：最新价被缩放，使累计收益 = 总回报（含分红再投）。

    与前复权相反：从最早价向前回推累积因子，除权日之后的价格统一除以 close[i]/close[i-1]。
    """
    c = np.asarray(closes, dtype=float).copy()
    n = len(c)
    ex = np.asarray(ex_rights, dtype=bool)
    factor = np.ones(n, dtype=float)
    for i in range(1, n):
        factor[i] = factor[i - 1]
        if ex[i] and c[i - 1] > 0:
            factor[i] *= c[i - 1] / c[i]
    return c * factor
