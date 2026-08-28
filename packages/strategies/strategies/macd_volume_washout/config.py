"""MACD 水下多头 + 极缩量（washout）策略配置。

实测依据（/tmp/macd_vol_cross.py，74,945 样本，持有 5 日，基线胜率约 44.57%）：
    MACD 水下（DIF<0）+ 多头（DIF>DEA）+ vr60<0.6 → **+9.39pp**（n=6080，均收益 +0.72%），
    是「MACD 状态 × 量能」交叉矩阵里最强的组合；同区间 vr60 0.6-0.9 也 +8.46pp。
    而 5 日基准（vr5）缩量区间超额为负——量比基准窗口是关键，60 日才单调有效
    （见 docs/因子研究报告.md）。

本策略把该组合固化为独立选股策略：缩量到 60 日均量 60% 以下、且 MACD 处于
「水下但已多头」阶段（抛压衰竭、DIF 拐头）的标的，赌超卖后的均值回归反弹。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MacdVolumeWashoutConfig(BaseModel):
    """MACD 水下多头 + 极缩量策略的可调阈值。"""

    min_bars: int = Field(
        60, description="最少历史 K 线根数（需覆盖 60 日量比基准窗口）"
    )
    volume_ratio_window: int = Field(
        60, description="量比基准窗口（过去 N 日平均成交量，不含当日）"
    )
    volume_ratio_max: float = Field(
        0.6, description="量比上限：当日量 / 60 日均量 < 0.6 视为极缩量"
    )
    min_amount: float = Field(
        50_000_000.0, description="20 日均成交额下限（元，5000 万），剔除流动性不足"
    )
    # 市场环境档（阶段 9）：均值回归类 = 避开强涨/火爆/深跌，要清淡市。
    regime_profile: str = Field(
        "mean_reversion", description="适用的 regime 过滤档（mean_reversion/deep_accumulation/none）"
    )


def default_config() -> MacdVolumeWashoutConfig:
    """返回默认配置实例。"""
    return MacdVolumeWashoutConfig()
