"""单针下30（PIN30）策略配置。

口径来自 moomoo PIN30 指标（`us_pin30_watchlist.py::calc_pin30`，A股适配）：

    ST_RAW = EMA(EMA(C,10),10)
    LT_RAW = (MA14 + MA28 + MA57 + MA114) / 4
    短期   = (C - LLV(L,3))  / (HHV(C,3)  - LLV(L,3))  * 100
    长期   = (C - LLV(L,20)) / (HHV(C,20) - LLV(L,20)) * 100
    趋势多头 = ST_RAW > LT_RAW 且 C > LT_RAW
    PIN30  = 趋势多头 且 短期 <= 30 且 长期 >= 80

另叠加 TOOLS.md 的 KDJ 口径：J < 16 = B1_W 超卖。

说明：TOOLS.md 里「单针下30(K≤30 且 D≥80)」的 K/D 实际指 moomoo 的短期/长期
两条随机指标线（非 KDJ 的 K/D）。KDJ(9,3,3) 的 K≤30 且 D≥80 几乎不可能同时
成立（D 追 K 太快，全市场 0 命中），故按参考脚本 us_pin30_watchlist 的随机
指标口径实现，详见 docs/策略迁移说明.md。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Pin30Config(BaseModel):
    """单针下30（moomoo 随机指标口径）策略的可调阈值。"""

    short_lookback: int = Field(3, description="短期随机指标回看窗口（LLV/HHV）")
    long_lookback: int = Field(20, description="长期随机指标回看窗口")
    short_threshold: float = Field(30.0, description="短期 <= 30 视为急跌超卖")
    long_threshold: float = Field(80.0, description="长期 >= 80 视为长期仍强势")
    st_period: int = Field(10, description="ST_RAW = EMA(EMA(C,N),N) 的周期")
    lt_periods: tuple[int, int, int, int] = Field(
        (14, 28, 57, 114), description="LT_RAW 的四条均线周期"
    )
    j_b1w_threshold: float = Field(16.0, description="J < 16 视为 B1_W 超卖")
    min_bars: int = Field(120, description="最少历史 K 线根数（需覆盖 MA114）")
    # 市场环境档（阶段 9）：均值回归类。
    regime_profile: str = Field(
        "mean_reversion", description="适用的 regime 过滤档（mean_reversion/deep_accumulation/none）"
    )


def default_config() -> Pin30Config:
    """返回默认配置实例。"""
    return Pin30Config()
