"""偷涨型（水下二次金叉）策略配置。

阈值来源：`~/.openclaw/workspace/tools/stealth_rally_scanner.py`。

注意：旧脚本 `has_recent_limit_up` 用 ``r[5]``（成交额 amount）当昨收，导致
「近10日无涨停」过滤形同虚设（永远不触发），本策略已按正确口径（昨收）修复，
详见 docs/策略迁移说明.md 的「旧脚本 bug 修复」一节。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StealthRallyConfig(BaseModel):
    """偷涨型策略的可调阈值。"""

    min_bars: int = Field(60, description="最少需要的历史 K 线根数，不足则跳过")
    max_cross_age: int = Field(
        60, description="水下金叉距今日的最大天数，超过则不算偷涨（旧脚本 --days 默认 60）"
    )
    limit_up_lookback: int = Field(10, description="检查最近 N 日是否有涨停")
    limit_up_pct: float = Field(9.5, description="涨跌幅（%）达到此阈值视为涨停（主板 9.5≈10）")
    # 市场环境档（阶段 9）：均值回归类（水下二次金叉，埋伏型）。
    regime_profile: str = Field(
        "mean_reversion", description="适用的 regime 过滤档（mean_reversion/deep_accumulation/none）"
    )


def default_config() -> StealthRallyConfig:
    """返回默认配置实例。"""
    return StealthRallyConfig()
