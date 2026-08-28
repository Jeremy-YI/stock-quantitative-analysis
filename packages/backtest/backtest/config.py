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
from market.regime import should_allow as _regime_should_allow

# 默认持有期（交易日）：对应 Jeremy 现用 top5_verify 的「持有 N 日」验证
DEFAULT_HOLD_DAYS = (1, 3, 5, 10, 20)

# 默认策略仓位权重（阶段 7 按「20 日超额胜率」推导，阶段 8 改用「超额收益」，
# 见 docs/信号叠加分析.md）。推导公式：weight = max(0, 20 日超额收益)，单位百分点。
#   实测（2026-03-01 ~ 08-27，修复仓位分配缺陷后）：
#   etf_accumulation +6.25%、stealth_rally +1.65% 为正超额收益；其余 ≤ 0 → 权重 0。
# 阶段 8 修复了组合回测 FIFO 建仓缺陷（按策略分资金池 + 策略内按 score 排序），
# 权重从「超额胜率」改为「超额收益」后，结论变为「etf 主配 + 偷涨次配」——
# 详见 docs/信号叠加分析.md §3。
DEFAULT_STRATEGY_WEIGHTS: dict[str, float] = {
    "etf_accumulation": 6.25,
    "stealth_rally": 1.65,
    "double_bottom": 0.0,
    "b1b2b3": 0.0,
    "macd_resonance": 0.0,
    "pin30": 0.0,
    "macd_volume_washout": 0.0,
}


def default_strategy_weights() -> dict[str, float]:
    """返回按实测超额胜率推导的默认策略权重（供加权组合回测使用）。"""
    return dict(DEFAULT_STRATEGY_WEIGHTS)


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


class RegimeFilterConfig(BaseModel):
    """组合回测的市场环境（regime）过滤条件——只在允许的市场状态下开仓。

    默认值依据实测（docs/市场环境模块说明.md）：
        - 大盘 20 日涨幅 < +4%（上涨市中均值回归组合超额转负）
        - 活跃度 < 1.2（火爆市超额最差）
        - 回撤在 -15%~0（中跌区间均值回归组合超额转负）
    任一指标缺失 / NaN 时视为不允许（数据不足保守）。
    """

    max_index_20d_return: float = Field(0.04, description="大盘 20 日涨幅上限")
    max_activity: float = Field(1.2, description="市场活跃度上限（总成交量/60日均量）")
    min_drawdown: float = Field(-0.15, description="距 120 日高点回撤下限")
    max_drawdown: float = Field(0.0, description="距 120 日高点回撤上限")

    def allow(
        self, index_20d_return: float | None, activity: float | None, drawdown: float | None
    ) -> bool:
        """判断是否允许开仓（委托 market.regime.should_allow）。"""
        return _regime_should_allow(
            index_20d_return,
            activity,
            drawdown,
            max_index_20d_return=self.max_index_20d_return,
            max_activity=self.max_activity,
            min_drawdown=self.min_drawdown,
            max_drawdown=self.max_drawdown,
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
    strategy_weights: dict[str, float] | None = Field(
        None,
        description=(
            "各策略仓位权重（阶段 8 改为按 20 日超额收益推导，见 docs/信号叠加分析.md）。"
            "None = 等权（各策略均分资金池，每策略按 score 取前 N）；"
            "给定后，资金池按 w/sum(w) 切分，未列出的策略权重为 0（不建仓）。"
        ),
    )
    # 市场环境过滤：None = 不过滤（旧行为）；给定后只在允许的市场状态下开仓。
    regime_filter: RegimeFilterConfig | None = Field(
        None, description="市场环境过滤条件（见 market.regime 与 docs/市场环境模块说明.md）"
    )


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
