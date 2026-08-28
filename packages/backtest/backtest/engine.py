"""回测引擎：把策略信号串成「验证报告 / 组合净值 / 衰减曲线」。

三种能力：

    1. ``run_verification``  信号验证模式（对应 top5_verify.py）：
       每个信号算持有 N 日的收益，按策略 / 板块聚合截面统计。
    2. ``run_portfolio``     组合回测模式：按信号建仓 → 净值曲线。
    3. ``compute_decay``     策略衰减监测：滚动窗口（交易日）胜率曲线。

板块归属：先按市场板块（主板 / 创业板 / 科创板 / 北交所）做简化映射，
真实行业板块（申万 / 东方财富）需名称快照，列为后续 TODO（见 docs）。
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd

from market.calendar import trading_days

from .config import BacktestConfig, default_config
from .forward import forward_returns
from .models import (
    BacktestReport,
    BoardResult,
    DecayPoint,
    DecaySeries,
    HoldReturn,
    PortfolioReport,
    StrategyResult,
    VerificationReport,
)
from .portfolio import simulate_portfolio
from .stats import histogram, summarize_returns

# 简化板块映射（代码前缀 → 市场板块）。TODO: 接真实行业板块数据。
_BOARD_PREFIXES = (
    ("68", "科创板"),
    ("30", "创业板"),
    ("60", "沪市主板"),
    ("00", "深市主板"),
    ("43", "北交所"),
    ("83", "北交所"),
    ("87", "北交所"),
    ("88", "北交所"),
    ("92", "北交所"),
)


def classify_board(symbol: str) -> str:
    """按代码前缀返回简化市场板块。未知归「其他」。"""
    for prefix, board in _BOARD_PREFIXES:
        if symbol.startswith(prefix):
            return board
    return "其他"


class CandlesProvider(Protocol):
    """回测取数接口：按代码返回全量日线（含 date/open/high/low/close）。"""

    def get(self, symbol: str) -> pd.DataFrame | None: ...


class DictCandlesProvider:
    """基于 dict 的内存取数实现（测试 / 扫描结果直接用）。"""

    def __init__(self, candles: dict[str, pd.DataFrame]) -> None:
        self._candles = candles

    def get(self, symbol: str) -> pd.DataFrame | None:
        return self._candles.get(symbol)


class BacktestEngine:
    """信号 → 回测报告的编排器。"""

    def __init__(
        self,
        candles: CandlesProvider | None = None,
        config: BacktestConfig | None = None,
    ) -> None:
        self._candles = candles or DictCandlesProvider({})
        self._config = config or default_config()

    # ------------------------------------------------------------------
    # 信号验证模式
    # ------------------------------------------------------------------
    def run_verification(self, signals: list) -> VerificationReport:
        """对一批信号算持有 N 日收益并聚合。"""
        cfg = self._config

        # 每信号算 forward returns（缓存 DataFrame 避免重复读）
        df_cache: dict[str, pd.DataFrame] = {}
        rows: list[tuple] = []  # (strategy, board, signal_date, hold_returns)
        for s in signals:
            df = df_cache.get(s.symbol)
            if s.symbol not in df_cache:
                df = self._candles.get(s.symbol)
                df_cache[s.symbol] = df
            if df is None or df.empty:
                continue
            fr = forward_returns(df, s.triggered_at, cfg.hold_days)
            rows.append((s.strategy, classify_board(s.symbol), s.triggered_at, fr))

        by_strategy = self._aggregate_by_group(
            rows, key_idx=0, name_field="strategy", as_strategy=True
        )
        by_board = self._aggregate_by_group(
            rows, key_idx=1, name_field="board", as_strategy=False
        )
        decay = self.compute_decay(signals, rows)

        return VerificationReport(
            total_signals=len(signals),
            hold_days=list(cfg.hold_days),
            by_strategy=by_strategy,
            by_board=by_board,
            decay=decay,
        )

    def _aggregate_by_group(
        self, rows: list[tuple], key_idx: int, name_field: str, as_strategy: bool
    ):
        """按策略 / 板块聚合截面统计。"""
        from collections import defaultdict

        groups: dict[str, list[tuple]] = defaultdict(list)
        for r in rows:
            groups[r[key_idx]].append(r)

        out: list = []
        for name in sorted(groups):
            group_rows = groups[name]
            holds: list[HoldReturn] = []
            for n in self._config.hold_days:
                returns = [r[3][n] for r in group_rows if r[3].get(n) is not None]
                stats = summarize_returns(returns)
                holds.append(
                    HoldReturn(
                        hold_days=n,
                        n=stats.n,
                        win_rate=round(stats.win_rate, 4),
                        avg_return=round(stats.avg_return, 4),
                        median_return=round(stats.median_return, 4),
                        profit_loss_ratio=(
                            round(stats.profit_loss_ratio, 4)
                            if stats.profit_loss_ratio is not None
                            else None
                        ),
                        std=round(stats.std, 4),
                        best=round(stats.best, 4),
                        worst=round(stats.worst, 4),
                        quantiles=stats.quantiles,
                        histogram=histogram(returns),
                    )
                )
            if as_strategy:
                out.append(StrategyResult(strategy=name, holds=holds))
            else:
                out.append(BoardResult(board=name, holds=holds))
        return out

    # ------------------------------------------------------------------
    # 组合回测模式
    # ------------------------------------------------------------------
    def run_portfolio(self, signals: list) -> PortfolioReport:
        """按信号模拟组合，输出净值曲线。"""
        candles_map = {s.symbol: self._candles.get(s.symbol) for s in signals}
        candles_map = {k: v for k, v in candles_map.items() if v is not None}
        raw = simulate_portfolio(signals, candles_map, self._config)
        return PortfolioReport(
            equity_curve=[{"date": p["date"], "equity": p["equity"]} for p in raw["equity_curve"]],
            total_return=round(raw["total_return"], 4),
            max_drawdown=round(raw["max_drawdown"], 4),
            sharpe=round(raw["sharpe"], 4) if raw["sharpe"] is not None else None,
            trade_count=raw["trade_count"],
            filled_buys=raw["filled_buys"],
            skipped_buys=raw["skipped_buys"],
            open_positions=raw["open_positions"],
        )

    # ------------------------------------------------------------------
    # 一次跑完整报告（验证 + 组合）
    # ------------------------------------------------------------------
    def run(self, signals: list, with_portfolio: bool = True) -> BacktestReport:
        """一次算出验证报告（含衰减），可选叠加组合净值。"""
        verification = self.run_verification(signals)
        portfolio = self.run_portfolio(signals) if with_portfolio else None
        return BacktestReport(verification=verification, portfolio=portfolio)

    # ------------------------------------------------------------------
    # 策略衰减监测
    # ------------------------------------------------------------------
    def compute_decay(
        self, signals: list, rows: list[tuple] | None = None
    ) -> list[DecaySeries]:
        """滚动窗口（交易日）胜率曲线。

        用「汇总持有期 decay_hold_days」的正收益占比，按交易日滑动窗口
        （decay_windows 里每个长度各出一条曲线）。
        """
        cfg = self._config
        if rows is None:
            df_cache: dict[str, pd.DataFrame] = {}
            rows = []
            for s in signals:
                if s.symbol not in df_cache:
                    df_cache[s.symbol] = self._candles.get(s.symbol)
                df = df_cache[s.symbol]
                if df is None or df.empty:
                    continue
                fr = forward_returns(df, s.triggered_at, [cfg.decay_hold_days])
                rows.append((s.strategy, classify_board(s.symbol), s.triggered_at, fr))

        # 只保留有有效 decay 收益的信号，按策略分组
        from collections import defaultdict

        by_strategy: dict[str, list[tuple[date, int]]] = defaultdict(list)
        for strategy, _board, d, fr in rows:
            ret = fr.get(cfg.decay_hold_days)
            if ret is None:
                continue
            by_strategy[strategy].append((d, 1 if ret > 0 else 0))

        out: list[DecaySeries] = []
        for strategy in sorted(by_strategy):
            entries = sorted(by_strategy[strategy], key=lambda x: x[0])
            if not entries:
                continue
            # 交易日序数：从最早信号日到最晚信号日
            min_d = entries[0][0]
            max_d = entries[-1][0]
            day_list = trading_days(min_d, max_d)
            ord_map = {d: i for i, d in enumerate(day_list)}

            # 按交易日聚合每日 wins / n
            per_day: dict[date, tuple[int, int]] = {}
            for d, w in entries:
                ww, nn = per_day.get(d, (0, 0))
                per_day[d] = (ww + w, nn + 1)

            for window in cfg.decay_windows:
                points: list[DecayPoint] = []

                for d in day_list:
                    if d not in per_day:
                        continue
                    # 窗口起点：d 往前 window-1 个交易日
                    start_ord = ord_map[d] - (window - 1)
                    if start_ord < 0:
                        start_ord = 0
                    wins = 0
                    n = 0
                    for dd, (w, nn) in per_day.items():
                        if dd in ord_map and start_ord <= ord_map[dd] <= ord_map[d]:
                            wins += w
                            n += nn
                    if n == 0:
                        continue
                    points.append(
                        DecayPoint(
                            date=d, window=window, win_rate=round(wins / n, 4), n=n
                        )
                    )
                out.append(
                    DecaySeries(
                        strategy=strategy,
                        hold_days=cfg.decay_hold_days,
                        window=window,
                        points=points,
                    )
                )
        return out
