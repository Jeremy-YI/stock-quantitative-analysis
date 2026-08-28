"""RSI 相对强弱指标计算。

公式（标准 Wilder 平滑，与本地脚本 `daily_stock_picker.py::calc_rsi` 一致）：

    涨跌幅 delta = close[i] - close[i-1]
    gain = max(delta, 0)，loss = max(-delta, 0)
    初始 avg_gain = 前 period 根 gain 的简单平均（Wilder 首值）
    初始 avg_loss = 前 period 根 loss 的简单平均
    之后 Wilder 递推：
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    RS  = avg_gain / avg_loss
    RSI = 100 - 100 / (1 + RS)

前 ``period`` 根没有足够涨跌幅，用中性值 50 填充（与旧脚本一致）。
输出与输入等长。

与旧脚本的唯一差异：avg_gain 与 avg_loss 同时为 0（完全无波动）时，
旧脚本返回 100，标准定义为 50（中性），此处按标准修正，详见 docs/指标迁移说明.md。
"""

from __future__ import annotations

from typing import Sequence

# 指标参数
RSI_PERIOD = 14  # RSI 周期
NEUTRAL_RSI = 50.0  # 数据不足 / 无波动时的中性填充值


def calc_rsi(closes: Sequence[float], period: int = RSI_PERIOD) -> list[float]:
    """计算 RSI 序列（Wilder 平滑）。

    纯函数：不读文件、不发请求、不抛业务异常。
    空输入返回空列表；长度不足 ``period + 1`` 时返回全中性值的等长列表。

    Args:
        closes: 收盘价序列。
        period: 周期（默认 14），必须为正整数。

    Returns:
        与输入等长的 RSI 序列。前 ``period`` 根为 50.0 填充。

    Raises:
        ValueError: period 非正数时抛出。
    """
    if period <= 0:
        raise ValueError(f"period 必须为正整数，收到 {period}")

    n = len(closes)
    if n == 0:
        return []
    if n < period + 1:
        return [NEUTRAL_RSI] * n

    # 涨跌幅拆成 gain / loss 两列（长度 n-1）
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, n):
        delta = closes[i] - closes[i - 1]
        gains.append(delta if delta > 0 else 0.0)
        losses.append(-delta if delta < 0 else 0.0)

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # 前 period 根无 RSI，填中性值；第 period+1 根才有首值
    rsi = [NEUTRAL_RSI] * period
    rsi.append(_rsi_from_averages(avg_gain, avg_loss))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rsi.append(_rsi_from_averages(avg_gain, avg_loss))

    return rsi


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    """由 avg_gain/avg_loss 计算 RSI 值，处理除零边界。

    - avg_loss == 0 且 avg_gain > 0：无下跌 → RSI = 100（超买极值）
    - avg_loss == 0 且 avg_gain == 0：完全无波动 → RSI = 50（中性，标准定义）
    - 其余：RSI = 100 - 100 / (1 + avg_gain / avg_loss)
    """
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else NEUTRAL_RSI
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)
