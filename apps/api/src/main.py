"""股市量化平台 REST API 入口。

运行方式（仓库根目录，先完成 `make install`）：

    uvicorn main:app --reload

暴露端点：
    GET /api/v1/health
    GET /api/v1/indicators/{macd,kdj,rsi,volume}?symbol=...&start=&end=
    GET /api/v1/strategies
    GET /api/v1/strategies/{name}/scan?date=YYYY-MM-DD
    GET /api/v1/strategies/{name}/signals?from=&to=
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.settings import Settings, get_settings
from errors import (
    DomainError,
    InsufficientDataError,
    SymbolNotFoundError,
    UnknownJobError,
    UnknownStrategyError,
)
from repositories.backtest_repository import (
    BacktestRunRepository,
    InMemoryBacktestRunRepository,
)
from repositories.daily_bar_repository import DailyBarRepository, TdxDailyBarRepository
from repositories.scan_result_repository import (
    InMemoryScanResultRepository,
    ScanResultRepository,
)
from routers import backtest, dashboard, health, indicators, research, scheduler, sectors, strategies
from services.backtest_service import BacktestService
from services.dashboard_service import DashboardService
from services.indicator_service import IndicatorService
from services.research_service import ResearchService
from services.scheduler_service import SchedulerService
from services.sector_service import SectorService
from services.strategy_service import StrategyService
from strategies.scanner import MarketScanner, Scanner

API_PREFIX = "/api/v1"


def _register_exception_handlers(app: FastAPI) -> None:
    """领域异常 → HTTP 状态码（400/404/422），响应统一用 { message }。"""

    @app.exception_handler(SymbolNotFoundError)
    async def _symbol_not_found(_request: Request, exc: SymbolNotFoundError):
        return JSONResponse(status_code=404, content={"message": str(exc)})

    @app.exception_handler(UnknownStrategyError)
    async def _unknown_strategy(_request: Request, exc: UnknownStrategyError):
        return JSONResponse(status_code=404, content={"message": str(exc)})

    @app.exception_handler(UnknownJobError)
    async def _unknown_job(_request: Request, exc: UnknownJobError):
        return JSONResponse(status_code=404, content={"message": str(exc)})

    @app.exception_handler(InsufficientDataError)
    async def _insufficient_data(_request: Request, exc: InsufficientDataError):
        return JSONResponse(status_code=422, content={"message": str(exc)})

    @app.exception_handler(DomainError)
    async def _domain_error(_request: Request, exc: DomainError):
        return JSONResponse(status_code=400, content={"message": str(exc)})


def create_app(
    settings: Settings | None = None,
    repository: DailyBarRepository | None = None,
    strategy_scanner: Scanner | None = None,
    scan_repository: ScanResultRepository | None = None,
    backtest_repository: BacktestRunRepository | None = None,
    scheduler_instance=None,
) -> FastAPI:
    """应用工厂：测试可传入自定义 settings / fake 仓储 / fake 扫描器 / fake 调度器。"""
    settings = settings or get_settings()

    app = FastAPI(title="stock-api", version="0.1.0")

    # 依赖注入：service 挂到 app.state，路由里通过 Depends 取用
    repo = repository or TdxDailyBarRepository(settings.hsjday_path)
    app.state.service = IndicatorService(repo)

    scanner = strategy_scanner or MarketScanner(settings.hsjday_path)
    scan_repo = scan_repository or InMemoryScanResultRepository()
    app.state.strategy_service = StrategyService(scanner, scan_repo)

    backtest_repo = backtest_repository or InMemoryBacktestRunRepository()
    app.state.backtest_service = BacktestService(scanner, backtest_repo, settings)

    sched = scheduler_instance or _build_default_scheduler(settings)
    app.state.scheduler_service = SchedulerService(sched)
    app.state.dashboard_service = DashboardService(
        settings.dashboard_snapshot_path_resolved, app.state.scheduler_service
    )
    app.state.research_service = ResearchService(settings.research_snapshot_path_resolved)
    app.state.sector_service = SectorService()

    _register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(dashboard.router, prefix=API_PREFIX)
    app.include_router(indicators.router, prefix=API_PREFIX)
    app.include_router(strategies.router, prefix=API_PREFIX)
    app.include_router(backtest.router, prefix=API_PREFIX)
    app.include_router(scheduler.router, prefix=API_PREFIX)
    app.include_router(research.router, prefix=API_PREFIX)
    app.include_router(sectors.router, prefix=API_PREFIX)
    return app


def _build_default_scheduler(settings: Settings):
    """用 settings 组装默认调度器（MySQL 仓储 + 真实 scanner + AKShare 客户端）。

    所有 MySQL 仓储都是惰性连接（首次 save/query 才连库），AKShare 客户端也是
    惰性 import，故这里构造不触发网络 / DB。
    """
    from scheduler.executor import JobExecutor
    from scheduler.jobs.akshare_client import AkshareLiveClient
    from scheduler.jobs.etl_repository import MySqlEtlRepository
    from scheduler.jobs.registry import (
        build_a_share_registry,
        default_notifier_factory,
    )
    from scheduler.jobs.sinks import MySqlScanSink
    from scheduler.repository import MySqlRunRepository
    from scheduler.scheduler import Scheduler
    from scheduler.sharding import MySqlShardTracker

    scanner = MarketScanner(settings.hsjday_path)
    run_repo = MySqlRunRepository()
    shard_tracker = MySqlShardTracker()
    sink = MySqlScanSink()
    etl_repo = MySqlEtlRepository()
    akshare_client = AkshareLiveClient()

    registry = build_a_share_registry(
        scanner, sink, shard_tracker, etl_repo, akshare_client
    )
    notifier_factory = default_notifier_factory(
        settings.scheduler_report_dir, settings.feishu_webhook_url or None
    )
    executor = JobExecutor(run_repo, notifier_factory=notifier_factory)
    return Scheduler(registry, executor, run_repo)


app = create_app()
