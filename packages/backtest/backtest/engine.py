"""回测引擎：把策略信号串成「验证报告 / 组合净值 / 衰减曲线」。

三种能力：

    1. ``run_verification``  信号验证模式（对应 top5_verify.py）：
       每个信号算持有 N 日的收益，按策略 / 板块聚合截面统计，并附上
       「同期同宇宙基线」对比（超额胜率 / 超额收益，见 backtest.baseline）。
    2. ``run_portfolio``     组合回测模式：按信号建仓 → 净值曲线。
    3. ``compute_decay``     策略衰减监测：滚动窗口（交易日）胜率曲线，
       同时给出「超额胜率」滚动曲线（原始胜率下降可能只是市场变差）。

板块归属：先按市场板块（主板 / 创业板 / 科创板 / 北交所）做简化映射，
真实行业板块（申万 / 东方财富）需名称快照，列为后续 TODO（见 docs）。

选择性 / 超额口径（阶段 4.5 引入，见 docs/回测迁移说明.md）：

    - 基线按「宇宙种类」分开算（个股 / ETF），策略对各自目标宇宙的基线。
    - selectivity = 日均信号数 / 宇宙标的数（每天触发了该宇宙的百分之几）。
    - excess_win_rate = 策略胜率 - 同期同宇宙基线胜率（真正衡量「有没有超额」）。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from typing import Protocol

import pandas as pd

from market.calendar import trading_days
from market.regime import compute_market_series

from .baseline import daily_baseline_win_rates, compute_baseline
from .config import BacktestConfig, default_config
from .forward import forward_returns
from .models import (
    BacktestReport,
    BaselineHold,
    BaselineResult,
    BoardResult,
    DecayPoint,
    DecaySeries,
    HoldReturn,
    OverlayCell,
    PortfolioReport,
    StrategyResult,
    VerificationReport,
)
from .overlay import compute_overlay
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


def _kind_value(kind) -> str:
    """把 SymbolKind 枚举或普通字符串归一化成 'stock'/'etf' 字符串。"""
    return getattr(kind, "value", kind)


class CandlesProvider(Protocol):
    """回测取数接口：按代码返回全量日线（含 date/open/high/low/close）。"""

    def get(self, symbol: str) -> pd.DataFrame | None: ...


class DictCandlesProvider:
    """基于 dict 的内存取数实现（测试 / 扫描结果直接用）。"""

    def __init__(self, candles: dict[str, pd.DataFrame]) -> None:
        self._candles = candles

    def get(self, symbol: str) -> pd.DataFrame | None:
        return self._candles.get(symbol)

    def all(self) -> dict[str, pd.DataFrame]:
        """返回全部标的日线（供 regime 计算取全市场数据）。"""
        return self._candles


class BacktestEngine:
    """信号 → 回测报告的编排器。"""

    def __init__(
        self,
        candles: CandlesProvider | None = None,
        config: BacktestConfig | None = None,
        kind_map: dict[str, str] | None = None,
    ) -> None:
        self._candles = candles or DictCandlesProvider({})
        self._config = config or default_config()
        # 标的 → 宇宙种类（"stock"/"etf" 或 SymbolKind 枚举）。用于基线分宇宙计算。
        self._kind_map = kind_map or {}

    # ------------------------------------------------------------------
    # 信号验证模式
    # ------------------------------------------------------------------
    def run_verification(
        self,
        signals: list,
        start: date | None = None,
        end: date | None = None,
    ) -> VerificationReport:
        """对一批信号算持有 N 日收益并聚合（含基线 / 选择性 / 超额）。"""
        cfg = self._config

        # 区间：未显式给定时从信号日期推导（基线要与信号同期）
        if start is None or end is None:
            ds = [s.triggered_at for s in signals]
            if ds:
                start = start or min(ds)
                end = end or max(ds)

        # 基线：按宇宙种类（个股 / ETF）分开算
        baselines = self._compute_baselines(start, end)
        baseline_by_kind = {
            b.universe: {h.hold_days: h for h in b.holds} for b in baselines
        }

        # 宇宙规模 + 策略 → 宇宙种类 + 日均信号数（选择性指标用）
        kind_counts: dict[str, int] = Counter(_kind_value(k) for k in self._kind_map.values())
        strategy_kind: dict[str, str] = {}
        for s in signals:
            kind = self._kind_map.get(s.symbol)
            if kind is not None:
                strategy_kind.setdefault(s.strategy, _kind_value(kind))
        signal_counts: dict[str, int] = Counter(s.strategy for s in signals)
        n_days = len(trading_days(start, end)) if start and end else 0

        # 每信号算 forward returns（缓存 DataFrame 避免重复读）
        df_cache: dict[str, pd.DataFrame] = {}
        rows: list[tuple] = []  # (strategy, board, signal_date, hold_returns)
        for s in signals:
            if s.symbol not in df_cache:
                df_cache[s.symbol] = self._candles.get(s.symbol)
            df = df_cache[s.symbol]
            if df is None or df.empty:
                continue
            fr = forward_returns(df, s.triggered_at, cfg.hold_days)
            rows.append((s.strategy, classify_board(s.symbol), s.triggered_at, fr))

        agg_kwargs = dict(
            baseline_by_kind=baseline_by_kind,
            strategy_kind=strategy_kind,
            kind_counts=kind_counts,
            n_days=n_days,
            signal_counts=signal_counts,
        )
        by_strategy = self._aggregate_by_group(
            rows, key_idx=0, name_field="strategy", as_strategy=True, **agg_kwargs
        )
        by_board = self._aggregate_by_group(
            rows, key_idx=1, name_field="board", as_strategy=False
        )
        decay = self.compute_decay(
            signals, rows, baseline_by_kind=baseline_by_kind, strategy_kind=strategy_kind
        )

        overlay = self._compute_overlay(signals, baseline_by_kind)

        return VerificationReport(
            total_signals=len(signals),
            hold_days=list(cfg.hold_days),
            by_strategy=by_strategy,
            by_board=by_board,
            decay=decay,
            baselines=baselines,
            overlay=overlay,
        )

    def _compute_baselines(
        self, start: date | None, end: date | None
    ) -> list[BaselineResult]:
        """按宇宙种类（个股 / ETF）分别计算同期基线。无宇宙信息时返回空。"""
        if start is None or end is None or not self._kind_map:
            return []

        groups: dict[str, set[str]] = defaultdict(set)
        for symbol, kind in self._kind_map.items():
            groups[_kind_value(kind)].add(symbol)

        out: list[BaselineResult] = []
        for universe in sorted(groups):
            stats = compute_baseline(
                self._candles,
                groups[universe],
                universe,
                start,
                end,
                self._config.hold_days,
            )
            out.append(
                BaselineResult(
                    universe=universe,
                    size=stats.size,
                    holds=[
                        BaselineHold(
                            hold_days=h.hold_days,
                            n=h.n,
                            win_rate=round(h.win_rate, 6),
                            avg_return=round(h.avg_return, 6),
                            median_return=round(h.median_return, 6),
                        )
                        for h in stats.holds
                    ],
                )
            )
        return out

    def _aggregate_by_group(
        self,
        rows: list[tuple],
        key_idx: int,
        name_field: str,
        as_strategy: bool,
        baseline_by_kind: dict[str, dict[int, BaselineHold]] | None = None,
        strategy_kind: dict[str, str] | None = None,
        kind_counts: dict[str, int] | None = None,
        n_days: int = 0,
        signal_counts: dict[str, int] | None = None,
    ):
        """按策略 / 板块聚合截面统计（策略层附带基线超额 + 选择性）。"""
        groups: dict[str, list[tuple]] = defaultdict(list)
        for r in rows:
            groups[r[key_idx]].append(r)

        baseline_by_kind = baseline_by_kind or {}
        strategy_kind = strategy_kind or {}
        kind_counts = kind_counts or {}
        signal_counts = signal_counts or {}

        out: list = []
        for name in sorted(groups):
            group_rows = groups[name]
            holds: list[HoldReturn] = []
            for n in self._config.hold_days:
                returns = [r[3][n] for r in group_rows if r[3].get(n) is not None]
                stats = summarize_returns(returns)

                # 超额：只有策略层有宇宙种类时才对比基线
                baseline_hold = None
                if as_strategy:
                    universe = strategy_kind.get(name)
                    if universe and universe in baseline_by_kind:
                        baseline_hold = baseline_by_kind[universe].get(n)

                excess_win_rate = None
                excess_return = None
                baseline_win_rate = None
                baseline_avg_return = None
                if baseline_hold is not None:
                    baseline_win_rate = baseline_hold.win_rate
                    baseline_avg_return = baseline_hold.avg_return
                    excess_win_rate = round(
                        stats.win_rate - baseline_hold.win_rate, 4
                    )
                    excess_return = round(
                        stats.avg_return - baseline_hold.avg_return, 4
                    )

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
                        baseline_win_rate=baseline_win_rate,
                        baseline_avg_return=baseline_avg_return,
                        excess_win_rate=excess_win_rate,
                        excess_return=excess_return,
                    )
                )
            if as_strategy:
                universe = strategy_kind.get(name)
                universe_size = kind_counts.get(universe) if universe else None
                sig_count = signal_counts.get(name, 0)
                signals_per_day = sig_count / n_days if n_days else None
                selectivity = None
                if signals_per_day is not None and universe_size:
                    selectivity = round(signals_per_day / universe_size, 6)
                out.append(
                    StrategyResult(
                        strategy=name,
                        universe=universe,
                        universe_size=universe_size,
                        signals_per_day=(
                            round(signals_per_day, 3)
                            if signals_per_day is not None
                            else None
                        ),
                        selectivity=selectivity,
                        holds=holds,
                    )
                )
            else:
                out.append(BoardResult(board=name, holds=holds))
        return out

    def _compute_overlay(
        self, signals: list, baseline_by_kind: dict[str, dict[int, BaselineHold]]
    ) -> list[OverlayCell]:
        """算两两策略叠加矩阵（阶段 7）。基线胜率已由 _compute_baselines 算出。"""
        if not signals:
            return []
        kind_str = {sym: _kind_value(k) for sym, k in self._kind_map.items()}
        base_win = {
            universe: {hd: bh.win_rate for hd, bh in holds.items()}
            for universe, holds in baseline_by_kind.items()
        }
        headline = self._config.hold_days[-1] if self._config.hold_days else 20
        cells = compute_overlay(signals, self._candles, kind_str, base_win, headline_hold=headline)
        return [OverlayCell(**c) for c in cells]

    # ------------------------------------------------------------------
    # 组合回测模式
    # ------------------------------------------------------------------
    def run_portfolio(self, signals: list) -> PortfolioReport:
        """按信号模拟组合，输出净值曲线。

        若 ``config.portfolio.regime_filter`` 给定，则从全市场 candles 计算
        市场环境序列并传入组合回测，只在允许的市场状态下开仓。
        """
        candles_map = {s.symbol: self._candles.get(s.symbol) for s in signals}
        candles_map = {k: v for k, v in candles_map.items() if v is not None}
        regime_series = None
        if (
            self._config.portfolio.regime_filter is not None
            or self._config.portfolio.regime_by_strategy
        ):
            regime_series = self._compute_regime_series()
        raw = simulate_portfolio(signals, candles_map, self._config, regime_series=regime_series)
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

    def _compute_regime_series(self) -> pd.DataFrame | None:
        """从全市场 candles 算等权市场序列（仅个股宇宙，排除 ETF）。"""
        provider = self._candles
        if not hasattr(provider, "all"):
            return None
        candles = provider.all()
        # 只取个股宇宙（ETF 波动小、会稀释等权指数的择时信号）
        stock_candles = {
            sym: df
            for sym, df in candles.items()
            if self._kind_map.get(sym) is None
            or _kind_value(self._kind_map.get(sym)) == "stock"
        }
        series = compute_market_series(stock_candles)
        return series if not series.empty else None

    # ------------------------------------------------------------------
    # 一次跑完整报告（验证 + 组合）
    # ------------------------------------------------------------------
    def run(
        self,
        signals: list,
        with_portfolio: bool = True,
        start: date | None = None,
        end: date | None = None,
    ) -> BacktestReport:
        """一次算出验证报告（含衰减），可选叠加组合净值。"""
        verification = self.run_verification(signals, start=start, end=end)
        portfolio = self.run_portfolio(signals) if with_portfolio else None
        return BacktestReport(verification=verification, portfolio=portfolio)

    # ------------------------------------------------------------------
    # 策略衰减监测
    # ------------------------------------------------------------------
    def compute_decay(
        self,
        signals: list,
        rows: list[tuple] | None = None,
        baseline_by_kind: dict[str, dict[int, BaselineHold]] | None = None,
        strategy_kind: dict[str, str] | None = None,
    ) -> list[DecaySeries]:
        """滚动窗口（交易日）胜率曲线（含超额胜率）。

        用「汇总持有期 decay_hold_days」的正收益占比，按交易日滑动窗口
        （decay_windows 里每个长度各出一条曲线）。同时给出超额胜率：
        策略滚动胜率 − 同期同宇宙基线滚动胜率（每日基线胜率的窗口均值）。
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
        by_strategy: dict[str, list[tuple[date, int]]] = defaultdict(list)
        for strategy, _board, d, fr in rows:
            ret = fr.get(cfg.decay_hold_days)
            if ret is None:
                continue
            by_strategy[strategy].append((d, 1 if ret > 0 else 0))

        # 全局区间（用于算每日基线胜率）
        all_dates = [d for strategy, _b, d, _fr in rows]
        gmin = min(all_dates) if all_dates else None
        gmax = max(all_dates) if all_dates else None

        # 每个宇宙种类的「当日基线胜率」序列（供超额对比）
        daily_base_by_kind: dict[str, dict[date, float]] = {}
        if gmin and gmax and self._kind_map:
            groups: dict[str, set[str]] = defaultdict(set)
            for symbol, kind in self._kind_map.items():
                groups[_kind_value(kind)].add(symbol)
            for kind, syms in groups.items():
                daily = daily_baseline_win_rates(
                    self._candles, syms, gmin, gmax, [cfg.decay_hold_days]
                )
                daily_base_by_kind[kind] = daily.get(cfg.decay_hold_days, {})

        strategy_kind = strategy_kind or {}

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

            base_daily = daily_base_by_kind.get(strategy_kind.get(strategy), {})

            for window in cfg.decay_windows:
                points: list[DecayPoint] = []
                for d in day_list:
                    if d not in per_day:
                        continue
                    start_ord = ord_map[d] - (window - 1)
                    if start_ord < 0:
                        start_ord = 0
                    wins = 0
                    n = 0
                    base_wins_sum = 0.0
                    base_n = 0
                    for dd, (w, nn) in per_day.items():
                        if dd in ord_map and start_ord <= ord_map[dd] <= ord_map[d]:
                            wins += w
                            n += nn
                    # 基线：窗口内每日基线胜率的均值（市场广度口径）
                    if base_daily:
                        for dd, bw in base_daily.items():
                            if dd in ord_map and start_ord <= ord_map[dd] <= ord_map[d]:
                                base_wins_sum += bw
                                base_n += 1
                    win_rate = wins / n if n else 0.0
                    baseline_win_rate = (
                        base_wins_sum / base_n if base_n else None
                    )
                    excess_win_rate = (
                        round(win_rate - baseline_win_rate, 4)
                        if baseline_win_rate is not None
                        else None
                    )
                    points.append(
                        DecayPoint(
                            date=d,
                            window=window,
                            win_rate=round(win_rate, 4),
                            n=n,
                            baseline_win_rate=(
                                round(baseline_win_rate, 4)
                                if baseline_win_rate is not None
                                else None
                            ),
                            excess_win_rate=excess_win_rate,
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
