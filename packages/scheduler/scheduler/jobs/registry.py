"""A股任务注册表 + 调度栈组装。

把阶段 5 要迁移的 A股任务声明成 ``JobSpec`` 注册进 ``JobRegistry``，并把共享
依赖（scanner / sink / shard tracker / ETL 仓储 / akshare client / 衰减提供者）
一次性接线。美股任务本阶段不迁，但 ``JobSpec`` 已留好扩展位（tags / cron / 时区
都是声明式的，加美股任务只需再注册几个 JobSpec）。
"""

from __future__ import annotations

from datetime import date, timedelta

from backtest.config import BacktestConfig, default_config as default_backtest_config
from backtest.engine import BacktestEngine, DictCandlesProvider
from strategies import REGISTRY
from strategies.filters import SymbolKind, filter_for_kinds
from strategies.scanner import Scanner

from scheduler.jobs.a_share import (
    _STRATEGY_NAMES,
    DecayProvider,
    daily_report,
    daily_scan,
    decay_check,
)
from scheduler.jobs.akshare_client import AkshareClient
from scheduler.jobs.etl import etl_etf_flow, etl_sector_flow, etl_st_snapshot
from scheduler.jobs.etl_repository import EtlRepository
from scheduler.jobs.sinks import ScanSink
from scheduler.models import JobResult, JobSpec, NotifierKind
from scheduler.notifier import FileNotifier, Notifier, WebhookNotifier
from scheduler.registry import JobRegistry
from scheduler.sharding import ShardTracker

# 超额胜率历史参考（静态值，来自 docs/回测迁移说明.md 的 20 日超额胜率，2026-03~08）
# 仅作每日报告展示，非实时计算；实时计算见 weekly_decay_check 任务。
EXCESS_REFERENCE: dict[str, float | None] = {
    "b1b2b3": -0.5,
    "macd_resonance": -12.9,
    "pin30": -2.1,
    "stealth_rally": 6.8,
    "etf_accumulation": 31.5,
}


def build_engine_decay_provider(
    scanner: Scanner,
    sink: ScanSink,
    window: int = 20,
    hold_days: int = 1,
    lookback_days: int = 60,
) -> DecayProvider:
    """构造「近 window 日超额胜率」提供者（复用阶段 4.5 的回测引擎）。"""

    def provider() -> dict[str, float | None]:
        end = date.today()
        start = end - timedelta(days=lookback_days)

        # 收集历史信号 + 标的宇宙种类
        signals: list = []
        kind_map: dict[str, str] = {}
        for name in _STRATEGY_NAMES:
            mod = REGISTRY[name]
            kind = mod.TARGET_KINDS[0].value if mod.TARGET_KINDS else None
            for s in sink.get_signals(name, start, end):
                signals.append(s)
                if kind:
                    kind_map.setdefault(s.symbol, kind)

        if not signals:
            return {}

        # 按宇宙种类分别加载 candles
        candles: dict = {}
        stock_syms = {s for s, k in kind_map.items() if k == "stock"}
        etf_syms = {s for s, k in kind_map.items() if k == "etf"}
        if stock_syms:
            candles.update(
                scanner.load_candles(
                    end, filter_config=filter_for_kinds((SymbolKind.STOCK,)),
                    symbols=stock_syms,
                )
            )
        if etf_syms:
            candles.update(
                scanner.load_candles(
                    end, filter_config=filter_for_kinds((SymbolKind.ETF,)),
                    symbols=etf_syms,
                )
            )

        config = default_backtest_config()
        config.decay_hold_days = hold_days
        config.decay_windows = [window]
        engine = BacktestEngine(DictCandlesProvider(candles), config, kind_map=kind_map)

        result: dict[str, float | None] = {}
        for series in engine.compute_decay(signals):
            if series.window == window and series.points:
                result[series.strategy] = series.points[-1].excess_win_rate
        return result

    return provider


def build_a_share_registry(
    scanner: Scanner,
    sink: ScanSink,
    shard_tracker: ShardTracker,
    etl_repo: EtlRepository,
    akshare_client: AkshareClient,
    decay_provider: DecayProvider | None = None,
    excess_reference: dict[str, float | None] | None = None,
) -> JobRegistry:
    """组装 A股任务注册表（本阶段只迁 A股，美股留扩展位）。"""
    decay_provider = decay_provider or build_engine_decay_provider(scanner, sink)
    excess_reference = EXCESS_REFERENCE if excess_reference is None else excess_reference

    registry = JobRegistry()

    registry.register(
        JobSpec(
            name="daily_scan",
            description="每日收盘全市场扫描（五策略，分片 + 断点续跑）",
            cron="30 15 * * 1-5",
            timeout_seconds=1200,
            max_retries=1,
            retry_backoff_seconds=60,
            notifier=NotifierKind.FILE,
            tags=["A股"],
            target=daily_scan,
            kwargs={
                "scanner": scanner,
                "sink": sink,
                "shard_tracker": shard_tracker,
                "job_name": "daily_scan",
                "shard_size": 500,
            },
        )
    )

    registry.register(
        JobSpec(
            name="daily_report",
            description="每日选股报告（各策略信号 + 超额胜率历史参考）",
            cron="0 16 * * 1-5",
            timeout_seconds=300,
            max_retries=0,
            notifier=NotifierKind.WEBHOOK,
            tags=["A股"],
            target=daily_report,
            kwargs={"sink": sink, "excess_reference": excess_reference},
        )
    )

    registry.register(
        JobSpec(
            name="weekly_decay_check",
            description="周度策略衰减检查（超额胜率滚动统计，近 20 日超额转负标红）",
            cron="0 17 * * 6",
            timeout_seconds=1800,
            max_retries=0,
            notifier=NotifierKind.WEBHOOK,
            tags=["A股"],
            target=decay_check,
            kwargs={"decay_provider": decay_provider},
        )
    )

    registry.register(
        JobSpec(
            name="post_market_etl",
            description="盘后 ETL：板块资金流 + ETF 资金流落 MySQL（AKShare）",
            cron="35 15 * * 1-5",
            timeout_seconds=600,
            max_retries=1,
            retry_backoff_seconds=30,
            notifier=NotifierKind.FILE,
            tags=["A股", "ETL"],
            target=_etl_combined,
            kwargs={"client": akshare_client, "repo": etl_repo},
        )
    )

    registry.register(
        JobSpec(
            name="st_snapshot",
            description="ST 名单快照落库（供 strategies.filters 的 ST 过滤）",
            cron="40 15 * * 1-5",
            timeout_seconds=300,
            max_retries=0,
            notifier=NotifierKind.FILE,
            tags=["A股", "ETL"],
            target=etl_st_snapshot,
            kwargs={"client": akshare_client, "repo": etl_repo},
        )
    )

    return registry


def _etl_combined(ctx, client, repo) -> JobResult:
    """盘后 ETL 组合：板块 + ETF 资金流一起拉，一次跑完。"""
    sector = etl_sector_flow(ctx, client=client, repo=repo)
    etf = etl_etf_flow(ctx, client=client, repo=repo)
    combined = f"{sector.summary}；{etf.summary}"
    report = ""
    if sector.report_markdown and etf.report_markdown:
        report = sector.report_markdown + "\n\n" + etf.report_markdown
    return JobResult(
        summary=combined,
        report_title="盘后 ETL（板块 + ETF 资金流）",
        report_markdown=report,
    )


def default_notifier_factory(
    file_dir: str, webhook_url: str | None
):
    """构造 notifier 工厂：按 JobSpec.notifier 返回 File / Webhook。"""

    def factory(job: JobSpec) -> Notifier | None:
        if job.notifier is NotifierKind.WEBHOOK:
            if not webhook_url:
                return None  # 未配置 webhook 时静默降级为不发送
            return WebhookNotifier(webhook_url)
        return FileNotifier(file_dir)

    return factory
