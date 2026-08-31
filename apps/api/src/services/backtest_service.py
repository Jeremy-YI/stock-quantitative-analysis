"""回测服务。

职责：按日期区间逐日扫描策略收集信号 → 组装回测引擎 → 出报告 → 落库。
不碰 HTTP，不直接读文件（通过扫描器），保持可单测。

性能说明：逐日全市场扫描成本较高（单日约 1 分钟，见 docs/策略迁移说明.md），
阶段 4 按任务书要求「同步执行即可」，不引入队列。大批量历史回测建议用
scripts/run_backtest.py 离线跑批，API 面向小范围演示与查询。
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from backtest.config import BacktestConfig, RegimeFilterConfig
from backtest.engine import BacktestEngine, DictCandlesProvider
from backtest.models import BacktestReport
from config.settings import Settings
from errors import DomainError, UnknownStrategyError
from market.calendar import trading_days
from repositories.backtest_repository import BacktestRunRepository
from schemas.backtest import BacktestRunBody, BacktestRunRequest, DecayBody
from strategies import REGISTRY
from strategies.filters import filter_for_kinds
from strategies.scanner import Scanner


class BacktestService:
    """回测发起 / 查询 / 衰减服务。"""

    def __init__(
        self,
        scanner: Scanner,
        repository: BacktestRunRepository,
        settings: Settings,
        jobs: dict | None = None,
    ) -> None:
        self._scanner = scanner
        self._repository = repository
        self._settings = settings
        self._jobs: dict = jobs if jobs is not None else {}

    def create_run_async(self, request: BacktestRunRequest) -> str:
        """注册一次回测任务并返回 run_id（不执行计算，立即返回）。"""
        strategies = self._resolve_strategies(request.strategy)
        if request.start > request.end:
            raise DomainError("回测起始日不能晚于结束日")
        return uuid4().hex

    def finish_run(self, run_id: str) -> BacktestRunBody:
        """真正执行一次回测（由后台线程调用），返回完整报告。"""
        return self.create_run(run_id)

    def create_run(self, request: BacktestRunRequest | str) -> BacktestRunBody:
        """执行一次回测并落库。

        request 可以是请求体（同步路径，测试/脚本用），也可以是 run_id（异步路径，
        由 create_run_async 先注册、后台线程再调 finish_run 执行）。
        """
        if isinstance(request, str):
            # 异步路径：run_id 已在 store 里占位，这里只补算报告
            job = self._jobs[request]
            req = BacktestRunRequest(
                strategy=job["strategy"],
                start=job["start"],
                end=job["end"],
                mode=job.get("mode", "verify"),
                hold_days=job.get("hold_days"),
                regime_filter=job.get("regime_filter", False),
            )
            run_id = request
            request = req
        else:
            run_id = uuid4().hex

        strategies = self._resolve_strategies(request.strategy)
        if request.start > request.end:
            raise DomainError("回测起始日不能晚于结束日")

        signals, candles, kind_map = self._collect_signals(strategies, request.start, request.end)
        config = BacktestConfig()
        if request.hold_days:
            config.hold_days = list(request.hold_days)
        if request.regime_filter:
            config.portfolio.regime_filter = RegimeFilterConfig()

        engine = BacktestEngine(
            DictCandlesProvider(candles), config, kind_map=kind_map
        )
        verification = engine.run_verification(
            signals, start=request.start, end=request.end
        )
        portfolio = engine.run_portfolio(signals) if request.mode == "portfolio" else None
        report = BacktestReport(verification=verification, portfolio=portfolio)

        run = BacktestRunBody(
            run_id=run_id,
            strategy=request.strategy,
            start=request.start,
            end=request.end,
            mode=request.mode,
            report=report,
        )
        self._repository.save(run)
        return run

    def get_run(self, run_id: str) -> BacktestRunBody:
        """查询已落库的回测任务。"""
        run = self._repository.get(run_id)
        if run is None:
            raise UnknownStrategyError(f"回测任务 {run_id} 不存在")
        return run

    def get_decay(
        self,
        strategy: str,
        window: int,
        hold_days: int = 1,
        start: date | None = None,
        end: date | None = None,
    ) -> DecayBody:
        """计算某策略的滚动胜率衰减曲线。"""
        self._resolve_strategies(strategy)  # 校验策略存在
        end = end or date.today()
        start = start or (end - timedelta(days=180))

        signals, candles, kind_map = self._collect_signals([strategy], start, end)
        config = BacktestConfig()
        config.decay_hold_days = hold_days
        config.decay_windows = [window]

        engine = BacktestEngine(
            DictCandlesProvider(candles), config, kind_map=kind_map
        )
        series_list = engine.compute_decay(signals)
        points = []
        for s in series_list:
            if s.strategy == strategy and s.window == window:
                points = s.points
                break

        return DecayBody(
            strategy=strategy,
            window=window,
            hold_days=hold_days,
            points=points,
        )

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _resolve_strategies(self, strategy: str | None) -> list[str]:
        """strategy 为 None 时返回全部策略；否则校验存在并返回单元素列表。"""
        if strategy is None:
            return list(REGISTRY)
        if strategy not in REGISTRY:
            raise UnknownStrategyError(f"策略 {strategy} 不存在")
        return [strategy]

    def _collect_signals(
        self, strategies: list[str], start: date, end: date
    ) -> tuple[list, dict, dict]:
        """逐日扫描策略，返回 (signals, candles, kind_map)。

        candles 按各策略目标宇宙加载（个股策略 vs ETF 策略分开），
        扫描时按日切片（只留 <= 当日），前向收益在引擎里用全量 candles 算。
        kind_map = {代码: 宇宙种类字符串}，供引擎分宇宙算基线。
        """
        symbols_by_strategy: dict[str, set[str]] = {}
        candles: dict = {}
        kind_map: dict[str, str] = {}
        for strategy in strategies:
            mod = REGISTRY[strategy]
            loaded = self._scanner.load_candles(
                end, filter_config=filter_for_kinds(mod.TARGET_KINDS)
            )
            symbols_by_strategy[strategy] = set(loaded.keys())
            # 目标宇宙种类：策略均针对单一宇宙（个股或 ETF）
            kind = mod.TARGET_KINDS[0].value if mod.TARGET_KINDS else None
            for symbol, df in loaded.items():
                candles.setdefault(symbol, df)
                if kind:
                    kind_map.setdefault(symbol, kind)

        signals: list = []
        for day in trading_days(start, end):
            for strategy in strategies:
                mod = REGISTRY[strategy]
                sliced = {
                    symbol: candles[symbol][candles[symbol]["date"] <= day]
                    for symbol in symbols_by_strategy[strategy]
                    if symbol in candles
                }
                signals.extend(mod.scan(sliced, day))

        return signals, candles, kind_map
