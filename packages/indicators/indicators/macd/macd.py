"""MACD 指标计算。

公式（与本地通达信 .day 脚本 `calc_macd` 保持一致）：

    EMA_N = EMA(close, N)，N=12/26，EMA 用首根收盘价做种子
    DIF   = EMA_12 - EMA_26
    DEA   = EMA(DIF, 9)
    柱(MACD) = (DIF - DEA) * 2

输出与输入等长（空输入返回空），供前端/回测直接对齐 K 线索引。
"""

from __future__ import annotations

from typing import NamedTuple, Sequence

# 指标参数（魔法数字统一收敛到这里，禁止散落在调用处）
FAST_PERIOD = 12  # 快线 EMA 周期
SLOW_PERIOD = 26  # 慢线 EMA 周期
SIGNAL_PERIOD = 9  # 信号线（DEA）周期
BAR_MULTIPLIER = 2.0  # 柱状图放大倍数（国内行情软件通用 2 倍）
MIN_BARS_FOR_MACD = SLOW_PERIOD  # 少于慢线周期根数，MACD 不具备参考意义


class MacdResult(NamedTuple):
    """MACD 计算结果。dif/dea/macd 三列均与输入 close 等长。"""

    dif: list[float]
    dea: list[float]
    macd: list[float]


def calc_ema(values: Sequence[float], period: int) -> list[float]:
    """指数移动平均。

    Args:
        values: 收盘价序列。
        period: 周期，必须为正整数。

    Returns:
        与输入等长的 EMA 序列。空输入返回空列表。

    Raises:
        ValueError: period 非正数时抛出。
    """
    if period <= 0:
        raise ValueError(f"period 必须为正整数，收到 {period}")
    if not values:
        return []

    k = 2.0 / (period + 1)
    result = [float(values[0])]  # 首值做种子（与通达信脚本一致）
    for value in values[1:]:
        result.append(float(value) * k + result[-1] * (1 - k))
    return result


def calc_macd(closes: Sequence[float]) -> MacdResult:
    """计算 MACD 的 DIF / DEA / 柱。

    纯函数：不读文件、不发请求、不抛业务异常。
    空输入返回三列空列表；非空输入返回与 closes 等长的三列。
    """
    if not closes:
        return MacdResult([], [], [])

    ema_fast = calc_ema(closes, FAST_PERIOD)
    ema_slow = calc_ema(closes, SLOW_PERIOD)
    dif = [fast - slow for fast, slow in zip(ema_fast, ema_slow)]
    dea = calc_ema(dif, SIGNAL_PERIOD)
    macd = [(d - e) * BAR_MULTIPLIER for d, e in zip(dif, dea)]
    return MacdResult(dif, dea, macd)
