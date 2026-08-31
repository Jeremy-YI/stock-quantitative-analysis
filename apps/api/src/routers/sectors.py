"""板块资金流 + 板块个股推荐路由。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from schemas.common import ApiResponse
from schemas.sector import (
    EtfFlowBody,
    ExcludedStock,
    RecommendationsBody,
    RecommendedStock,
    SectorFlowBody,
    SectorListBody,
)
from services.sector_service import SectorService
from services.stock_meta_service import StockMetaService
from services.strategy_rating_service import StrategyRatingService, risk_reasons
from services.strategy_service import StrategyService

router = APIRouter(tags=["sectors"])


def get_sector_service(request: Request) -> SectorService:
    """从应用状态取 sector service（测试时可注入 fake）。"""
    return request.app.state.sector_service


def get_stock_meta_service(request: Request) -> StockMetaService:
    """股票名称 / ST 服务。"""
    return request.app.state.stock_meta_service


def get_rating_service(request: Request) -> StrategyRatingService:
    """策略回测评级服务。"""
    return request.app.state.strategy_rating_service


def get_repository(request: Request):
    """日线仓储（风控要看当日 K 线形态）。"""
    return request.app.state.repository


def get_strategy_service(request: Request) -> StrategyService:
    """取 strategy service（板块推荐要用它扫成分股信号）。"""
    return request.app.state.strategy_service


@router.get("/sectors", response_model=ApiResponse[SectorListBody])
def list_sectors(
    service: SectorService = Depends(get_sector_service),
) -> ApiResponse[SectorListBody]:
    """板块列表（名称 + 成分股数）。"""
    return ApiResponse(message="ok", body=SectorListBody(sectors=service.list_sectors()))


@router.get("/sectors/flow", response_model=ApiResponse[SectorFlowBody])
def sector_flow(
    days: str = Query("即时", description="窗口：即时/3日排行/5日排行/10日排行/20日排行"),
    service: SectorService = Depends(get_sector_service),
) -> ApiResponse[SectorFlowBody]:
    """板块资金流：top20 净流入 + top20 净流出。"""
    return ApiResponse(message="ok", body=service.sector_flow(days))


@router.get("/sectors/etf-flow", response_model=ApiResponse[EtfFlowBody])
def etf_flow(
    top: int = Query(20, ge=1, le=50, description="每侧取前多少名"),
    service: SectorService = Depends(get_sector_service),
) -> ApiResponse[EtfFlowBody]:
    """ETF 资金流：净流入 / 净流出 TOP N（已过滤货币、债券、迷你盘）。

    路径必须写在 /sectors/{name} 之前，否则会被动态段吃掉。
    """
    return ApiResponse(message="ok", body=service.etf_flow(top))


@router.get("/sectors/{name}/recommendations", response_model=ApiResponse[RecommendationsBody])
def sector_recommendations(
    name: str,
    date_: date = Query(..., alias="date", description="扫描日（YYYY-MM-DD）"),
    include_st: bool = Query(
        False, description="是否包含 ST/退市整理期股票（默认不包含，不推荐给客户）"
    ),
    include_unverified: bool = Query(
        False,
        description="是否包含回测未过关的策略（默认不包含；root 内部查看时才打开）",
    ),
    skip_risk_filter: bool = Query(
        False, description="是否跳过风控过滤（放量长上影/放量阴线/追高），默认不跳"
    ),
    sector_service: SectorService = Depends(get_sector_service),
    strategy_service: StrategyService = Depends(get_strategy_service),
    meta: StockMetaService = Depends(get_stock_meta_service),
    ratings: StrategyRatingService = Depends(get_rating_service),
    repository=Depends(get_repository),
) -> ApiResponse[RecommendationsBody]:
    """板块成分股 × 战法信号。

    三道闸，缺一不可（Jeremy 2026-08-31 定）：
      1. **ST / 退市整理期**直接不进候选
      2. **只用回测过关的策略**（data/strategy_ratings.json 里 client_safe），
         回测不过关的策略即使触发也不给客户看（root 可用 include_unverified 打开）
      3. **风控过滤**：放量长上影 / 放量阴线 / 追高 命中即剔除，并如实回报原因
    """
    symbols = sector_service.get_constituents(name)
    total = len(symbols)
    if not include_st:
        symbols = meta.filter_tradable(symbols)
    excluded_st = total - len(symbols)

    # 闸门 2：按回测评级挑策略
    all_strategies = [info.name for info in strategy_service.list_strategies()]
    if include_unverified or not ratings.available():
        used = all_strategies
        blocked: list[str] = []
    else:
        used = [s for s in all_strategies if ratings.is_client_safe(s)]
        blocked = [s for s in all_strategies if s not in used]

    signals = []
    for strategy in used:
        signals.extend(strategy_service.scan_subset(strategy, date_, symbols))
    signals.sort(key=lambda s: s.score, reverse=True)

    stocks = _group_by_stock(signals, meta, ratings)

    # 闸门 3：风控过滤（只对候选股取数，不扫全市场）
    excluded_risk: list[ExcludedStock] = []
    if not skip_risk_filter:
        kept = []
        for item in stocks:
            try:
                df = repository.get_daily_bars(item.symbol, None, date_)
            except Exception:  # noqa: BLE001 - 取不到数据按不推荐处理
                excluded_risk.append(
                    ExcludedStock(symbol=item.symbol, name=item.name, reasons=["行情读取失败"])
                )
                continue
            reasons = risk_reasons(df, date_)
            if reasons:
                excluded_risk.append(
                    ExcludedStock(symbol=item.symbol, name=item.name, reasons=reasons)
                )
            else:
                kept.append(item)
        stocks = kept
        kept_symbols = {s.symbol for s in stocks}
        signals = [s for s in signals if s.symbol in kept_symbols]

    return ApiResponse(
        message="ok",
        body=RecommendationsBody(
            sector=name,
            date=date_,
            signals=signals,
            stocks=stocks,
            excluded_st=excluded_st,
            names_available=meta.available(),
            strategies_used=used,
            strategies_blocked=blocked,
            ratings_available=ratings.available(),
            excluded_risk=excluded_risk,
        ),
    )


@router.get("/stocks/{symbol}/signals", response_model=ApiResponse[RecommendationsBody])
def stock_signals(
    symbol: str,
    date_: date = Query(..., alias="date", description="扫描日（YYYY-MM-DD）"),
    strategy_service: StrategyService = Depends(get_strategy_service),
    meta: StockMetaService = Depends(get_stock_meta_service),
    ratings: StrategyRatingService = Depends(get_rating_service),
    repository=Depends(get_repository),
) -> ApiResponse[RecommendationsBody]:
    """单只个股的全部战法信号（详情页）。

    这里**不做评级过滤**：详情页是用来看清楚的，回测不过关的策略也要显示，
    但会把评级一起带出去，让前端标明「这条信号回测不过关」。
    风控命中项同样返回，避免看图时忽略放量长上影这类硬伤。
    """
    signals = []
    for info in strategy_service.list_strategies():
        signals.extend(strategy_service.scan_subset(info.name, date_, [symbol]))
    signals.sort(key=lambda s: s.score, reverse=True)

    excluded_risk: list[ExcludedStock] = []
    try:
        df = repository.get_daily_bars(symbol, None, date_)
        reasons = risk_reasons(df, date_)
    except Exception:  # noqa: BLE001
        reasons = ["行情读取失败"]
    if reasons:
        excluded_risk.append(
            ExcludedStock(symbol=symbol, name=meta.name(symbol), reasons=reasons)
        )

    return ApiResponse(
        message="ok",
        body=RecommendationsBody(
            sector="",
            date=date_,
            signals=signals,
            stocks=_group_by_stock(signals, meta, ratings),
            excluded_st=0,
            names_available=meta.available(),
            strategies_used=[info.name for info in strategy_service.list_strategies()],
            strategies_blocked=[],
            ratings_available=ratings.available(),
            excluded_risk=excluded_risk,
        ),
    )


def _group_by_stock(
    signals: list, meta: StockMetaService, ratings: StrategyRatingService
) -> list[RecommendedStock]:
    """信号列表 → 按股票聚合（带名称与策略评级，按最高分降序）。"""
    grouped: dict[str, list] = {}
    for sig in signals:
        grouped.setdefault(sig.symbol, []).append(sig)
    stocks = [
        RecommendedStock(
            symbol=symbol,
            name=meta.name(symbol),
            score=max(s.score for s in group),
            signals=group,
            ratings=sorted({ratings.rating(s.strategy) for s in group}),
        )
        for symbol, group in grouped.items()
    ]
    stocks.sort(key=lambda s: s.score, reverse=True)
    return stocks
