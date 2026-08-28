"""双底反弹（W 底）策略配置。

阈值来源：`~/.openclaw/workspace/tools/us_double_bottom.py`（Jeremy 的美股双底
扫描器），迁移到 A股口径时做了如下适配（详见 docs/双底反弹迁移说明.md）：

    - 流动性门槛：旧脚本用 ``closes * volume`` 近似「美元成交额」，A股 hsjday
      自带 ``amount``（成交额，元）列，直接用它，阈值按 A股 5000 万元/日设定。
    - 最低股价：旧脚本 ``MIN_PRICE = 5.0``（美元），A股沿用 5.0 元，但语义是
      「剔除低价股/仙股」，单位从美元变人民币。
    - 回撤甜点区：旧脚本 ``max(highs)`` 取全窗口（约 2~3 年）最高点当「1 年高点」，
      与注释不符；新实现显式取近 ``drawdown_window`` 个交易日最高点（默认 250 ≈ 1 年）。
    - 涨跌停 / T+1 / 复权：策略层只做形态识别，交易约束（一字涨停买不进、T+1、
      前复权）由 ``packages/backtest``（execution / portfolio / market.adjust）落实。

所有阈值收敛到本文件，策略逻辑里禁止出现裸数字。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DoubleBottomConfig(BaseModel):
    """双底反弹策略的可调阈值。"""

    # ── 摆动低点 ──
    swing_k: int = Field(
        6, description="摆动低点左右各需 k 根不低于它（越大低点越显著，对应旧脚本 SWING_K）"
    )
    recent: int = Field(
        12, description="右底必须在最近 N 根内（信号新鲜度，对应旧脚本 RECENT）"
    )

    # ── 两底间隔窗口 ──
    min_gap: int = Field(12, description="两个低点最小间隔（根），太近不算双底")
    max_gap: int = Field(90, description="两个低点最大间隔（根），太远形态失效")

    # ── 低点相似度容差 ──
    tol_higher: float = Field(
        0.03, description="右底 L2 最多比左底 L1 高 3%（底部齐平度上限）"
    )
    tol_lower: float = Field(
        0.03, description="右底 L2 最多比左底 L1 低 3%（允许小幅假破前低）"
    )

    # ── 颈线 ──
    min_rally: float = Field(
        0.12, description="颈线（两底之间最高点）相对底部至少抬升 12%（中间要有真实反弹）"
    )
    l2_low_zone: float = Field(
        1.05, description="右底必须 ≤ 近 60 日最低价 × 1.05（右底要落在低位区）"
    )
    max_above_neck: float = Field(
        0.15, description="现价超过颈线 15% 以上视为形态已走完，剔除"
    )
    require_breakout: bool = Field(
        False,
        description=(
            "颈线突破确认开关：True 时只出「现价已站上颈线」的确认信号（标准 W 底买点），"
            "False 时保留右底构筑/爬升/突破中全阶段（埋伏型，与旧脚本一致）。"
        ),
    )
    breakout_margin: float = Field(
        0.02, description="站上颈线判定：现价 > 颈线 × (1 + 2%) 视为已突破"
    )

    # ── 量能配合 ──
    vol_shrink_threshold: float = Field(
        0.8, description="右底附近均量 / 左底附近均量 < 0.8 视为缩量二次探底"
    )
    vol_window: int = Field(
        1, description="底部附近均量半径（根）：取 idx±vol_window 共 2*vol_window+1 根，默认 1 对应旧脚本 vol_at 的 idx±1 共 3 根"
    )

    # ── A股流动性 ──
    min_price: float = Field(5.0, description="最低股价（元），剔除仙股/低价股")
    min_amount: float = Field(
        50_000_000.0, description="20 日均成交额下限（元，5000 万），剔除流动性不足的标的"
    )

    # ── 回撤甜点区（TOOLS.md：25%~40% 是最佳入场区） ──
    drawdown_low: float = Field(25.0, description="回撤幅度下限（%），低于此不达甜点区")
    drawdown_high: float = Field(40.0, description="回撤幅度上限（%），高于此视为趋势破位")
    drawdown_window: int = Field(
        250, description="回撤基准：近 N 个交易日的最高价（250 ≈ 1 年）"
    )

    # ── 数据长度 ──
    min_bars: int = Field(150, description="最少历史 K 线根数，不足则跳过")


def default_config() -> DoubleBottomConfig:
    """返回默认配置实例。"""
    return DoubleBottomConfig()
