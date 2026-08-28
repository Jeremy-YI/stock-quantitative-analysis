"""因子研究层契约（/research 页面数据）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResearchBinRow(BaseModel):
    """单因子分档的一行（超额表）。"""

    factor: str = ""  # 因子名（如 vr60 / 完美多头）
    label: str = ""  # 分档标签
    n: int = 0
    win_rate: float = 0.0
    avg_return: float = 0.0
    excess_win_rate: float | None = None
    excess_return: float | None = None


class ResearchCrossCell(BaseModel):
    """因子交叉矩阵的一个单元格。"""

    row: str
    col: str
    n: int = 0
    win_rate: float = 0.0
    excess_win_rate: float | None = None


class ResearchRegimeLayer(BaseModel):
    """regime 分层的一行（趋势跟随 vs 均值回归）。"""

    dimension: str = ""  # index_20d / drawdown / activity
    label: str = ""
    baseline_win_rate: float = 0.0
    trend_n: int = 0
    trend_excess: float | None = None
    reversion_n: int = 0
    reversion_excess: float | None = None


class ResearchSummary(BaseModel):
    """因子研究汇总（由 scripts/run_research.py 离线生成，前端只读）。"""

    as_of: str | None = None
    sample: int = 0
    hold_days: int = 5
    baseline_win_rate: float | None = None
    single_factors: list[ResearchBinRow] = Field(default_factory=list)
    cross_matrix: list[ResearchCrossCell] = Field(default_factory=list)
    regime_layers: list[ResearchRegimeLayer] = Field(default_factory=list)
