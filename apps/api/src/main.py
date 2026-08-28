"""股市量化平台 REST API 入口。

运行方式（仓库根目录，先完成 `make install`）：

    uvicorn main:app --reload

暴露端点：
    GET /api/v1/health
    GET /api/v1/indicators/macd?symbol=600519&start=&end=
    GET /api/v1/indicators/kdj?symbol=600519&start=&end=
    GET /api/v1/indicators/rsi?symbol=600519&start=&end=
    GET /api/v1/indicators/volume?symbol=600519&start=&end=
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.settings import Settings, get_settings
from errors import DomainError, InsufficientDataError, SymbolNotFoundError
from repositories.daily_bar_repository import DailyBarRepository, TdxDailyBarRepository
from routers import health, indicators
from services.indicator_service import IndicatorService

API_PREFIX = "/api/v1"


def _register_exception_handlers(app: FastAPI) -> None:
    """领域异常 → HTTP 状态码（404 / 422），响应统一用 { message }。"""

    @app.exception_handler(SymbolNotFoundError)
    async def _symbol_not_found(_request: Request, exc: SymbolNotFoundError):
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
) -> FastAPI:
    """应用工厂：测试可传入自定义 settings 或 fake repository。"""
    settings = settings or get_settings()

    app = FastAPI(title="stock-api", version="0.1.0")

    # 依赖注入：service 挂到 app.state，路由里通过 Depends 取用
    repo = repository or TdxDailyBarRepository(settings.hsjday_path)
    app.state.service = IndicatorService(repo)

    _register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(indicators.router, prefix=API_PREFIX)
    return app


app = create_app()
