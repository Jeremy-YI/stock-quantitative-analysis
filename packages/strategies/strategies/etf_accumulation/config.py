"""ETF 连续吸筹（跌幅 + 底背离）策略配置。

阈值来源：TOOLS.md「ETF 入场监控规则」（Jeremy 2026-08-11）：

    - ETF 跌幅达到 25%-40%（相对近 60 日高点回撤）
    - 同时出现底背离（价格新低，但 MACD/RSI 未新低）

说明：`etf_consec_tracker.py` 的「连续净流入天数」是 akshare 主力资金流口径，
依赖外部数据源，本平台策略层只读本地 K 线，故按 TOOLS.md 的「跌幅 + 底背离」
规则实现，资金流版本列为后续 TODO（见 docs/策略迁移说明.md）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EtfAccumulationConfig(BaseModel):
    """ETF 连续吸筹策略的可调阈值。"""

    drawdown_min: float = Field(25.0, description="回撤幅度下限（%），ETF 需至少跌这么多")
    drawdown_max: float = Field(40.0, description="回撤幅度上限（%），跌过头视为趋势破位")
    drawdown_window: int = Field(60, description="回撤基准：近 N 日最高价")
    divergence_window: int = Field(20, description="底背离比较窗口：近 N 根 K 线")
    min_bars: int = Field(60, description="最少需要的历史 K 线根数，不足则跳过")


def default_config() -> EtfAccumulationConfig:
    """返回默认配置实例。"""
    return EtfAccumulationConfig()
