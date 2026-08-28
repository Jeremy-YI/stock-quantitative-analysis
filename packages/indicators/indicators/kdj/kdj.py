"""KDJ 随机指标计算。

公式（与本地脚本 `daily_stock_picker.py::calc_kdj` 保持一致，即通达信 KDJ(9,3,3)）：

    RSV = (close - LLV(low, N)) / (HHV(high, N) - LLV(low, N)) * 100
          （HHV == LLV 时 RSV 取 50，避免除零）
    K   = 2/3 * K[昨日] + 1/3 * RSV      （初始 K = 50）
    D   = 2/3 * D[昨日] + 1/3 * K        （初始 D = 50）
    J   = 3 * K - 2 * D

前 N-1 根没有完整窗口算 RSV，用中性值 50 填充（与旧脚本一致），
输出与输入等长，供前端/回测直接对齐 K 线索引。
"""

from __future__ import annotations

from typing import NamedTuple, Sequence

# 指标参数（魔法数字统一收敛到这里，禁止散落在调用处）
KDJ_PERIOD = 9  # RSV 回看周期 N
K_SMOOTHING = 3  # K 的平滑参数（SMA(K, 3, 1) → 权重 1/3）
D_SMOOTHING = 3  # D 的平滑参数（SMA(D, 3, 1) → 权重 1/3）
K_WEIGHT = 1.0 / K_SMOOTHING  # 新 RSV 对 K 的权重 = 1/3
D_WEIGHT = 1.0 / D_SMOOTHING  # 新 K 对 D 的权重 = 1/3
INITIAL_K = 50.0  # K 初始值（无历史时取中性）
INITIAL_D = 50.0  # D 初始值
FLAT_RSV = 50.0  # 最高=最低（无波动）时 RSV 取中性值
PAD_VALUE = 50.0  # 前 N-1 根无完整窗口时的填充值


class KdjResult(NamedTuple):
    """KDJ 计算结果。k/d/j 三列均与输入 close 等长。"""

    k: list[float]
    d: list[float]
    j: list[float]


def calc_kdj(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = KDJ_PERIOD,
) -> KdjResult:
    """计算 KDJ 三线。

    纯函数：不读文件、不发请求、不抛业务异常。
    输入序列长度必须一致；空输入返回三列空列表。
    前 ``period - 1`` 根用 50.0 填充，之后逐根递推。

    Args:
        highs: 最高价序列。
        lows: 最低价序列。
        closes: 收盘价序列。
        period: RSV 回看周期（默认 9），必须为正整数。

    Returns:
        与输入等长的 K/D/J 三列。

    Raises:
        ValueError: period 非正数，或三序列长度不一致时抛出。
    """
    if period <= 0:
        raise ValueError(f"period 必须为正整数，收到 {period}")
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError(
            f"highs/lows/closes 长度必须一致，收到 {len(highs)}/{len(lows)}/{len(closes)}"
        )
    if not closes:
        return KdjResult([], [], [])

    length = len(closes)
    k_values = [PAD_VALUE] * length
    d_values = [PAD_VALUE] * length
    j_values = [PAD_VALUE] * length

    k_prev = INITIAL_K
    d_prev = INITIAL_D
    for i in range(period - 1, length):
        window_high = max(highs[i - period + 1 : i + 1])
        window_low = min(lows[i - period + 1 : i + 1])
        if window_high == window_low:
            rsv = FLAT_RSV
        else:
            rsv = (closes[i] - window_low) / (window_high - window_low) * 100.0

        k = (1 - K_WEIGHT) * k_prev + K_WEIGHT * rsv
        d = (1 - D_WEIGHT) * d_prev + D_WEIGHT * k
        j = 3.0 * k - 2.0 * d

        k_values[i] = k
        d_values[i] = d
        j_values[i] = j
        k_prev = k
        d_prev = d

    return KdjResult(k_values, d_values, j_values)
