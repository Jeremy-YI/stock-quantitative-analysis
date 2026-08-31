"""AI 解读路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from schemas.ai import InterpretBody, InterpretResult
from schemas.common import ApiResponse
from services.llm_service import LlmService
from services.rag_service import RagService
from services.strategy_service import StrategyService

router = APIRouter(tags=["ai"])


def get_llm_service(request: Request) -> LlmService:
    return request.app.state.llm_service


def get_strategy_service(request: Request) -> StrategyService:
    return request.app.state.strategy_service


def get_rag_service(request: Request) -> RagService:
    return request.app.state.rag_service


@router.post("/ai/interpret", response_model=ApiResponse[InterpretResult])
def interpret(
    body: InterpretBody,
    llm: LlmService = Depends(get_llm_service),
    strategies: StrategyService = Depends(get_strategy_service),
    rag: RagService = Depends(get_rag_service),
) -> ApiResponse[InterpretResult]:
    """对一只票：先扫它的战法信号，再用 LLM 解读成人话。

    解读前先做检索增强（RAG）：把触发的战法名 + 代码当查询，从
    「策略定义 + 当日消息 + 事件」里检索最相关的背景，注入 prompt。
    """
    # 1) 扫这只票（只扫 1 只，快）
    signals: list = []
    for info in strategies.list_strategies():
        signals.extend(strategies.scan_subset(info.name, body.date, [body.symbol]))
    signals.sort(key=lambda s: s.score, reverse=True)

    # 2) RAG 检索背景（查询 = 触发信号名 + 代码）
    query = f"{body.symbol} " + " ".join(
        f"{s.strategy} {s.signal_type}" for s in signals
    )
    context = rag.build_context(query) if signals else ""

    # 3) LLM 解读（带背景）
    text = llm.interpret(body.symbol, signals, context=context)

    return ApiResponse(
        message="ok",
        body=InterpretResult(symbol=body.symbol, signals=signals, interpretation=text),
    )
