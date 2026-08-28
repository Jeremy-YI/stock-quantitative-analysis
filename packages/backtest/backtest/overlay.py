"""信号叠加分析：两两策略「同标的同日触发」的标的，算它们的超额胜率。

方法（阶段 7 核心产出，见 docs/信号叠加分析.md）：

    - 对每对策略 (A, B)，取 trigger[A] ∩ trigger[B]（同一只标的在同一天同时被两个
      策略选中的「标的-日」集合），算这些标的持有 headline_hold 日的正收益占比，
      再减去同期同宇宙基线胜率得到超额胜率。
    - 对角（A == B）= 该策略自身的信号（等价于单策略胜率）。
    - 只有触发过同一天的标的才有意义，n 过小（样本不足）时超额不可靠，调用方
      用 n 做显著性判断。

纯函数、无副作用：只依赖 ``forward_returns`` 与给定的 candles provider / 基线。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from .forward import forward_returns


def compute_overlay(
    signals: list,
    provider,
    kind_map: dict[str, str],
    baseline_by_kind: dict[str, dict[int, float]],
    headline_hold: int = 20,
) -> list[dict]:
    """算两两策略叠加矩阵。

    Args:
        signals: Signal 列表（含 symbol / strategy / triggered_at）。
        provider: 有 ``get(symbol) -> DataFrame | None`` 的取数器（含 date/close）。
        kind_map: {代码: 宇宙种类字符串（"stock"/"etf"）}，供分宇宙取基线。
        baseline_by_kind: {universe: {hold_days: 基线胜率}}（引擎里已算好）。
        headline_hold: 叠加分析用的持有期（默认 20 日）。

    Returns:
        list[dict]，每个 dict 含 strategy_a / strategy_b / n / win_rate /
        excess_win_rate（上下三角各一条，含对角）。
    """
    trigger: dict[str, set[tuple[str, date]]] = defaultdict(set)
    for s in signals:
        trigger[s.strategy].add((s.symbol, s.triggered_at))

    names = sorted(trigger)
    df_cache: dict[str, object] = {}

    cells: list[dict] = []
    for a in names:
        for b in names:
            if b < a:
                continue
            co = trigger[a] & trigger[b]
            universe = kind_map.get(next(iter(co))[0], "stock") if co else "stock"
            base_win = baseline_by_kind.get(universe, {}).get(headline_hold)

            returns: list[float] = []
            for symbol, d in co:
                if symbol not in df_cache:
                    df_cache[symbol] = provider.get(symbol)
                df = df_cache[symbol]
                if df is None or getattr(df, "empty", False):
                    continue
                r = forward_returns(df, d, [headline_hold])[headline_hold]
                if r is not None:
                    returns.append(r)

            win_rate = sum(1 for r in returns if r > 0) / len(returns) if returns else 0.0
            excess = (win_rate - base_win) if (base_win is not None and returns) else None
            cells.append(
                {
                    "strategy_a": a,
                    "strategy_b": b,
                    "n": len(returns),
                    "win_rate": round(win_rate, 4),
                    "excess_win_rate": round(excess, 4) if excess is not None else None,
                }
            )
    return cells
