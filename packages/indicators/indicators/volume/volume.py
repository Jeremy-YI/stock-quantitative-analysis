"""量能指标计算。

包含三类量能辅助指标，供策略层/前端使用：

1. 量能均线 MAVOL1 / MAVOL2：
       MAVOL1 = 5 日简单平均（含当日，窗口不足时用已有数据平均）
       MAVOL2 = 10 日简单平均（同上）
   与本地脚本 `kdj_b1_backtest_all.py::ma` 的 `ma(v,5)/ma(v,10)` 完全一致。

2. 量比 volume_ratio：
       量比 = 当日成交量 / 过去 5 日平均成交量（不含当日）
   与本地脚本 `daily_stock_picker.py` 的 `vr = vol_now / avol5` 一致
   （avol5 = 过去 5 日成交量均值，不含当日）。首根无前日可比，取中性 1.0。

3. 价量关系判定 classify_price_volume：
       价升/价跌 = 收盘价相对前一日；放量/缩量 = 当日成交量相对 MAVOL1（5 日均量）。
       四象限：价升量增 / 价升缩量 / 价跌放量 / 价跌缩量；另有 价平 / 量平 / 首根无数据。
"""

from __future__ import annotations

from typing import NamedTuple, Sequence

# 指标参数
MAVOL1_PERIOD = 5  # 量能均线 1（短）
MAVOL2_PERIOD = 10  # 量能均线 2（长）
VOLUME_RATIO_PERIOD = 5  # 量比基准：过去 N 日平均成交量（不含当日）
NEUTRAL_RATIO = 1.0  # 无前日可比时量比的中性值

# 价量关系标签（语义串，供策略判定与前端展示）
REL_PRICE_UP_VOLUME_UP = "价升量增"
REL_PRICE_UP_VOLUME_DOWN = "价升缩量"
REL_PRICE_DOWN_VOLUME_UP = "价跌放量"
REL_PRICE_DOWN_VOLUME_DOWN = "价跌缩量"
REL_PRICE_FLAT = "价平"
REL_VOLUME_FLAT = "量平"
REL_NO_DATA = "—"


class VolumeMaResult(NamedTuple):
    """量能均线结果。mavol1/mavol2 与输入 volume 等长。"""

    mavol1: list[float]
    mavol2: list[float]


def calc_volume_ma(volumes: Sequence[float]) -> VolumeMaResult:
    """计算 MAVOL1(5 日) / MAVOL2(10 日) 量能均线。

    纯函数。空输入返回两条空列表。窗口不足时用已有数据平均（与旧脚本一致），
    因此前几根也有值，输出始终与输入等长。
    """
    if not volumes:
        return VolumeMaResult([], [])
    return VolumeMaResult(
        _simple_ma(volumes, MAVOL1_PERIOD),
        _simple_ma(volumes, MAVOL2_PERIOD),
    )


def calc_volume_ratio(
    volumes: Sequence[float], period: int = VOLUME_RATIO_PERIOD
) -> list[float]:
    """计算量比序列（当日量 / 过去 N 日平均量，不含当日）。

    首根无前日可比，取 1.0；前 N 根窗口不足时用已有前日数据平均。
    输出与输入等长。
    """
    if not volumes:
        return []
    result: list[float] = []
    for i in range(len(volumes)):
        start = max(0, i - period)
        window = volumes[start:i]
        if not window:
            result.append(NEUTRAL_RATIO)
            continue
        avg = sum(window) / len(window)
        result.append(volumes[i] / avg if avg > 0 else NEUTRAL_RATIO)
    return result


def classify_price_volume(
    closes: Sequence[float], volumes: Sequence[float]
) -> list[str]:
    """判定每根 K 线的价量关系（四象限）。

    - 价升/价跌：``close[i]`` 相对 ``close[i-1]``。
    - 放量/缩量：``volume[i]`` 相对 MAVOL1（5 日均量，含当日）。

    返回与输入等长的中文标签序列；首根无前日可比，返回 ``REL_NO_DATA``。
    """
    if not closes or not volumes:
        return []
    if len(closes) != len(volumes):
        raise ValueError(
            f"closes/volumes 长度必须一致，收到 {len(closes)}/{len(volumes)}"
        )

    mavol1 = calc_volume_ma(volumes).mavol1
    relations: list[str] = [REL_NO_DATA] * len(closes)
    for i in range(1, len(closes)):
        price_diff = closes[i] - closes[i - 1]
        volume_diff = volumes[i] - mavol1[i]

        if price_diff > 0:
            if volume_diff > 0:
                relations[i] = REL_PRICE_UP_VOLUME_UP
            elif volume_diff < 0:
                relations[i] = REL_PRICE_UP_VOLUME_DOWN
            else:
                relations[i] = REL_VOLUME_FLAT
        elif price_diff < 0:
            if volume_diff > 0:
                relations[i] = REL_PRICE_DOWN_VOLUME_UP
            elif volume_diff < 0:
                relations[i] = REL_PRICE_DOWN_VOLUME_DOWN
            else:
                relations[i] = REL_VOLUME_FLAT
        else:
            relations[i] = REL_PRICE_FLAT
    return relations


def _simple_ma(values: Sequence[float], period: int) -> list[float]:
    """简单移动平均，窗口不足时用已有数据平均（输出与输入等长）。"""
    result: list[float] = []
    for i in range(len(values)):
        start = max(0, i - period + 1)
        window = values[start : i + 1]
        result.append(sum(window) / len(window))
    return result
