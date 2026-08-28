"""B1/B2/B3 策略配置。

阈值来源（见 docs/策略迁移说明.md）：
    - B1（超卖）：J < 16（`daily_stock_picker.py::p2_scoring` 的 B1 判定）
      或 K ≤ 30（TOOLS.md「单针下30」里的超卖口径）。
    - B2（右侧确认）：PCT ≥ 3.7% + 放量（量比 > 1.2）+ 阳线 + J 上行。
      PCT 阈值 3.7 来自 Jeremy 截图分析框架（TOOLS.md）。
    - B3（缩量洗盘中继）：量比 < 0.8 + 5 日振幅 < 8%。
      量比 < 0.8 来自旧脚本 `vr >= 0.8` 判缩量的补集。

所有阈值收敛到本文件，策略逻辑里禁止出现裸数字。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class B1B2B3Config(BaseModel):
    """B1/B2/B3 三信号的可调阈值。"""

    # B1 超卖
    j_b1_threshold: float = Field(
        16.0, description="J 值低于此阈值视为超卖（触发 B1 的 J<16 分支）"
    )
    k_b1_threshold: float = Field(
        30.0, description="K 值低于此阈值视为超卖（触发 B1 的 K≤30 分支）"
    )
    # B2 右侧确认
    pct_b2_threshold: float = Field(
        3.7, description="当日涨幅（%）下限，B2 右侧确认要求 PCT ≥ 3.7"
    )
    volume_ratio_b2_threshold: float = Field(
        1.2, description="放量判定：量比 > 1.2 视为放量（对应旧脚本 1.2 <= vr）"
    )
    # B3 缩量洗盘中继
    volume_ratio_b3_threshold: float = Field(
        0.8, description="缩量判定：量比 < 0.8 视为缩量洗盘（对应旧脚本 vr < 0.8）"
    )
    range_b3_threshold: float = Field(
        8.0, description="5 日振幅（%）上限，B3 要求振幅 < 8% 的窄幅整理"
    )
    min_bars: int = Field(10, description="最少需要的历史 K 线根数，不足则跳过")
    # 市场环境档（阶段 9）：均值回归类 = 避开强涨/火爆/深跌，要清淡市。
    # 见 market.regime.REGIME_PROFILES 与 docs/样本外验证报告.md。
    regime_profile: str = Field(
        "mean_reversion", description="适用的 regime 过滤档（mean_reversion/deep_accumulation/none）"
    )


def default_config() -> B1B2B3Config:
    """返回默认配置实例。"""
    return B1B2B3Config()
