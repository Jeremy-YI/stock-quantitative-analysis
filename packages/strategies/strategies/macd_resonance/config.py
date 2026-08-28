"""MACD 月线水上 + 周线底部金叉策略配置。

阈值来源：`~/.openclaw/workspace/tools/macd_monthly_water_weekly_goldencross.py`
（Jeremy 2026-08-19 定的「月线定方向 + 周线找买点」选股条件），详见
docs/策略迁移说明.md。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MacdResonanceConfig(BaseModel):
    """月周 MACD 共振策略的可调阈值。"""

    min_daily_bars: int = Field(
        150, description="日线最少根数，不足则无足够月线/周线数据，跳过"
    )
    min_monthly_bars: int = Field(30, description="月线最少根数（对应 MACD 慢线 26 的预热）")
    min_weekly_bars: int = Field(60, description="周线最少根数")
    monthly_dif_above: float = Field(
        0.0, description="月线 MACD 水上判定：月线 DIF > 0"
    )
    cross_lookback_weeks: int = Field(
        6, description="周线金叉回看窗口：最近 N 周内出现 DIF 上穿 DEA 才算"
    )
    cross_dif_below: float = Field(
        0.0, description="底部金叉判定：金叉发生当周 DIF < 0（水下）"
    )


def default_config() -> MacdResonanceConfig:
    """返回默认配置实例。"""
    return MacdResonanceConfig()
