"""旧脚本参考实现（仅用于一致性测试，不进生产代码）。

从 `~/.openclaw/workspace/tools/` 抽取的指标计算逻辑，与新实现
`packages/indicators` 逐个比对，确保策略迁移后数值不变。

这里的代码刻意保留旧脚本的算法原貌（包括变量命名与边界处理），
只在 docstring 里注明来源文件和已知问题。请勿在业务代码中 import 本模块。
"""

from __future__ import annotations

from typing import Sequence


def legacy_calc_kdj(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], n: int = 9
):
    """KDJ(9,3,3)，来自 `daily_stock_picker.py::calc_kdj`（共享库版本）。

    约定：前 n-1 根填充 50；初始 K=D=50；HHV==LLV 时 RSV=50。
    这是 A股脚本里事实上的标准实现，与 `us_indicators.py::calc_kdj`、
    `us_pin30_scanner.py::quick_kdj` 一致。
    """
    length = len(closes)
    if length < n:
        return [50] * length, [50] * length, [50] * length
    k_vals: list[float] = []
    d_vals: list[float] = []
    j_vals: list[float] = []
    k_prev, d_prev = 50.0, 50.0
    for i in range(n - 1, length):
        hh = max(highs[i - n + 1 : i + 1])
        ll = min(lows[i - n + 1 : i + 1])
        rsv = 50.0 if hh == ll else (closes[i] - ll) / (hh - ll) * 100
        k = 2 / 3 * k_prev + 1 / 3 * rsv
        d = 2 / 3 * d_prev + 1 / 3 * k
        j = 3 * k - 2 * d
        k_vals.append(k)
        d_vals.append(d)
        j_vals.append(j)
        k_prev, d_prev = k, d
    pad = [50.0] * (n - 1)
    return pad + k_vals, pad + d_vals, pad + j_vals


def legacy_calc_rsi(closes: Sequence[float], period: int = 14) -> list[float]:
    """RSI(14) Wilder 平滑，来自 `daily_stock_picker.py::calc_rsi`。

    注意：旧实现里 ``avg_loss == 0`` 一律返回 100（含 avg_gain 也为 0 的
    完全无波动情形），这是已知问题；新实现修正为无波动返回 50，详见迁移说明。
    """
    n = len(closes)
    if n < period + 1:
        return [50.0] * n

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, n):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    rsi: list[float] = [50.0] * period
    if avg_loss == 0:
        rsi.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsi.append(100 - 100 / (1 + rs))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100 - 100 / (1 + rs))

    return rsi


def legacy_ma(values: Sequence[float], period: int) -> list[float]:
    """简单移动平均（窗口不足时用已有数据平均），来自 `kdj_b1_backtest_all.py::ma`。

    也是量能均线 MAVOL1/MAVOL2 的参考实现。
    """
    length = len(values)
    result = [0.0] * length
    for i in range(length):
        start = max(0, i - period + 1)
        result[i] = sum(values[start : i + 1]) / (i - start + 1)
    return result


def legacy_volume_ratio_last(volumes: Sequence[float]) -> float:
    """量比（仅最后一根），来自 `daily_stock_picker.py` 的 `vr` 计算。

    ``vr = vol_now / avol5``，其中 ``avol5`` 为过去 5 日平均成交量（不含当日）。
    数据不足 6 根时旧脚本退化为返回 1.0。
    """
    if len(volumes) >= 6:
        avol5 = sum(volumes[-6:-1]) / 5
    else:
        avol5 = volumes[-1]
    vol_now = volumes[-1]
    return vol_now / avol5 if avol5 > 0 else 1.0
