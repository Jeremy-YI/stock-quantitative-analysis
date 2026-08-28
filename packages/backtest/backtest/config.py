"""回测引擎配置。

交易成本参数全部收敛到 :class:`CostConfig`，中文注释说明费率来源，
引擎逻辑里禁止出现裸费率。来源：

    - 佣金：默认万分之 2.5，单笔最低 5 元（券商常见默认）。
    - 印花税：卖出单边千分之 1（现行 A股标准，2023-08 起减半后仍为 0.1%）。
    - 过户费：沪市万分之 0.1，双边收取（深市 2022 年起并入登记费，此处按
      任务书口径只对沪市收取）。
    - 滑点：默认千分之 1，按开盘价成交时叠加。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from market.adjust import DEFAULT_ADJUST_MODE, AdjustMode

# 默认持有期（交易日）：对应 Jeremy 现用 top5_verify 的「持有 N 日」验证
DEFAULT_HOLD_DAYS = (1, 3, 5, 10, 20)


class CostConfig(BaseModel):
    """交易成本参数。"""

    commission_rate: float = Field(
        0.00025, description="佣金费率（万分之 2.5 = 0.00025），双边收取"
    )
    min_commission: float = Field(5.0, description="单笔最低佣金（元）")
    stamp_tax_rate: float = Field(
        0.001, description="印花税（卖出单边，千分之 1）"
    )
    transfer_fee_rate: float = Field(
        0.00001, description="过户费（沪市万分之 0.1，双边收取）"
    )
    slippage: float = Field(
        0.001, description="滑点（默认千分之 1，按开盘/收盘价成交时叠加）"
    )


class PortfolioConfig(BaseModel):
    """组合回测仓位规则（参考 TOOLS.md）。"""

    initial_cash: float = Field(1_000_000.0, description="初始资金（元）")
    position_weight: float = Field(
        0.20, description="单只标的最大仓位（个股 ≤ 20%，TOOLS.md）"
    )
    reserve_ratio: float = Field(
        0.20, description="保留预备队比例（最多只用 80% 资金，TOOLS.md）"
    )
    max_holding_days: int = Field(20, description="固定持有期上限（交易日）")
    stop_loss_pct: float = Field(-0.08, description="止损线（相对买入价，-8%）")
    take_profit_pct: float = Field(0.15, description="止盈线（相对买入价，+15%）")
    # TODO: 3-2-2-2 分步建仓尚未实现，当前按一次性建仓（position_weight）近似。
    #       分步建仓需按「首笔 30% + 三次 20%」分批在后续交易日挂单，属后续优化。


class BacktestConfig(BaseModel):
    """回测总配置。"""

    hold_days: list[int] = Field(
        default_factory=lambda: list(DEFAULT_HOLD_DAYS),
        description="信号验证模式的持有期（交易日）列表",
    )
    risk_free_rate: float = Field(
        0.02, description="无风险利率（年化，夏普比率用），可配"
    )
    adjust_mode: AdjustMode = Field(
        DEFAULT_ADJUST_MODE, description="复权模式（前复权为默认口径）"
    )
    cost: CostConfig = Field(default_factory=CostConfig)
    portfolio: PortfolioConfig = Field(default_factory=PortfolioConfig)
    # 策略衰减监测：滚动窗口长度（交易日），可配近 20 / 60
    decay_windows: list[int] = Field(default_factory=lambda: [20, 60])
    decay_hold_days: int = Field(
        1, description="衰减监测用的持有期（默认 1 日，对应 top5_verify 次日命中率）"
    )


def default_config() -> BacktestConfig:
    """返回默认回测配置。"""
    return BacktestConfig()
