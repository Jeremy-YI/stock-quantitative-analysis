"""因子研究模块：把 /tmp 下四个因子实验脚本工程化。

提供三类可复现、可扩展的分析能力：

    1. 单因子超额计算器（``factors.excess_by_bins`` / ``factors.excess_boolean``）：
       给定因子布尔序列或数值分档，输出各档超额 + 样本数。
    2. 因子交叉矩阵（``factors.cross_excess``）：两个因子分档的二维超额矩阵。
    3. regime 分层分析（``regime.layered_excess``）：按市场环境分档，对比
       「趋势跟随 / 均值回归」两类组合在各档的超额。

均线参数统一用 Jeremy 真实参数 5/13/25/75/120（见 ``dataset.MAS``，注意不是
TOOLS.md 里写的 10/25/60/120）。结果通过 ``scripts/run_research.py`` CLI 复现。
"""

from research.dataset import MAS, build_factor_dataset
from research.factors import (
    excess_boolean,
    excess_by_bins,
    cross_excess,
)
from research.regime import layered_excess

__all__ = [
    "MAS",
    "build_factor_dataset",
    "cross_excess",
    "excess_boolean",
    "excess_by_bins",
    "layered_excess",
]
