"""轻量 Agent：让模型能主动调工具（查指标 / 查资料）再综合回答。

按 ACP C3「Function Calling + ReAct」思路手写，不引入 LangChain/AgentScope：
- 工具用 OpenAI Function Calling 协议定义（JSON Schema）。
- 循环：调模型 → 有 tool_calls 就执行工具 → 回传结果 → 再调，直到模型给出最终文本。
"""

from __future__ import annotations

import json
import logging
from datetime import date

from services.indicator_service import IndicatorService
from services.llm_service import LlmService
from services.multi_model_service import MultiModelService
from services.rag_service import RagService
from services.strategy_service import StrategyService

logger = logging.getLogger(__name__)

# 最大工具调用轮数：防死循环
MAX_ROUNDS = 5

# Agent 系统提示：告诉模型「有工具可调、先查再答、别编造」
AGENT_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是一名 A 股短线策略助手，可以调用工具查询技术指标、战法信号和知识库资料，再给出分析。\n\n"
    "# 可用工具\n"
    "- get_indicators：查询一只股票的最新 MACD/KDJ/RSI/量能指标。\n"
    "- get_signals：查询一只股票在指定日期触发的所有战法信号。\n"
    "- list_strategies：列出平台内置的所有选股战法及说明。\n"
    "- retrieve_context：从知识库检索策略定义、财经消息、事件日历。\n\n"
    "# 工作方式\n"
    "1. 先判断回答用户问题需要哪些数据，再调用对应工具（通常先查指标，需要解释战法/信号时再查资料）。\n"
    "2. 拿到工具返回的数据后，基于数据作答；工具没返回的数字一律不要编造。\n"
    "3. 一次只调必要的工具，不要用相同参数重复调用。\n\n"
    "# 输出要求\n"
    "面向个人投资者，用通俗中文，先给结论再给理由，全文 200 字以内。"
)

# 多模型并行研判时，给「提议者」模型的系统提示
ANALYSIS_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是一名 A 股短线策略分析师。根据给定的一只股票的指标数据和背景资料，给出你的独立分析。\n\n"
    "# 输出\n"
    "用通俗中文，先给结论再给理由，200 字以内。\n\n"
    "# 约束\n"
    "- 只基于给定的数据，严禁编造数据里没有的价格、涨跌幅、成交量。\n"
    "- 数据不足就明说「数据不足」，不要脑补。"
)

# 工具定义（OpenAI Function Calling 协议）
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_indicators",
            "description": (
                "查询一只 A 股的最新 MACD/KDJ/RSI/量能等技术指标。"
                "当用户问某只股票的走势、指标、买卖点、超买超卖时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "6 位 A 股代码，如 600519",
                    }
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_signals",
            "description": (
                "查询一只股票在指定日期触发的所有战法信号。"
                "当用户问某只股票触发了什么信号、有没有买点时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "6 位 A 股代码，如 600519",
                    },
                    "as_of": {
                        "type": "string",
                        "description": "扫描日期 YYYY-MM-DD，缺省用最近交易日",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_strategies",
            "description": (
                "列出平台内置的所有选股战法及说明。"
                "当用户问有哪些策略/战法可选时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_context",
            "description": (
                "从知识库检索与问题相关的策略定义、财经消息、事件日历。"
                "当需要解释某个战法/信号含义时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索关键词，如战法名、信号名、行业主题",
                    }
                },
                "required": ["query"],
            },
        },
    },
]


class AgentService:
    """ReAct Agent：查询工具 + 综合解读。"""

    def __init__(
        self,
        llm: LlmService,
        indicators: IndicatorService,
        rag: RagService,
        strategies: StrategyService,
        multi: MultiModelService | None = None,
    ) -> None:
        self._llm = llm
        self._indicators = indicators
        self._rag = rag
        self._strategies = strategies
        self._multi = multi

    def run(self, symbol: str, question: str) -> str:
        """回答用户关于某只股票的问题（自动调工具）。"""
        messages: list[dict] = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": f"股票代码 {symbol}。用户问题：{question}"},
        ]

        for _ in range(MAX_ROUNDS):
            try:
                message = self._llm.chat_message(messages, tools=TOOLS)
            except Exception as exc:  # noqa: BLE001 - 降级：LLM 挂了也要给用户一句话
                logger.warning("Agent LLM 调用失败：%s", exc)
                return "AI 服务暂时不可用，请稍后再试。"

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                if self._multi:
                    return self._multi.analyze(
                        ANALYSIS_SYSTEM_PROMPT, self._build_analysis(messages)
                    )
                return message.get("content") or ""

            # 记录 assistant 的 tool_calls 消息，再逐条执行工具并回传结果
            messages.append(message)
            for call in tool_calls:
                name = call["function"]["name"]
                args = self._parse_args(call["function"].get("arguments"))
                result = self._execute_tool(name, args)
                messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": result}
                )

        return "分析步骤过多，请换个问法。"

    @staticmethod
    def _build_analysis(messages: list[dict]) -> str:
        """把收集到的上下文（问题 + 工具结果）拼成给多模型的分析输入。"""
        user_q = messages[1]["content"]
        tool_results = [m["content"] for m in messages if m.get("role") == "tool"]
        if not tool_results:
            return user_q
        return f"{user_q}\n\n已收集的数据：\n" + "\n\n".join(tool_results)

    # ------------------------------------------------------------------
    # 工具执行
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_args(raw: str | None) -> dict:
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}

    def _execute_tool(self, name: str, args: dict) -> str:
        if name == "get_indicators":
            return self._get_indicators(args.get("symbol", ""))
        if name == "get_signals":
            return self._get_signals(args.get("symbol", ""), args.get("as_of"))
        if name == "list_strategies":
            return self._list_strategies()
        if name == "retrieve_context":
            return self._retrieve_context(args.get("query", ""))
        return f"未知工具：{name}"

    def _get_indicators(self, symbol: str) -> str:
        """查最新 MACD/KDJ/RSI/量能，拼成一段紧凑文本给模型。"""
        if not symbol:
            return "缺少股票代码。"
        try:
            macd = self._indicators.get_macd(symbol, limit=30)
            kdj = self._indicators.get_kdj(symbol, limit=30)
            rsi = self._indicators.get_rsi(symbol, limit=30)
            vol = self._indicators.get_volume(symbol, limit=30)
        except Exception as exc:  # noqa: BLE001 - 数据缺失等，降级为可读文本
            logger.warning("get_indicators 失败（%s）：%s", symbol, exc)
            return f"无法获取 {symbol} 的指标数据（可能数据缺失）。"

        if not (macd.series and kdj.series and rsi.series and vol.series):
            return f"没有 {symbol} 的指标数据。"

        m = macd.series[-1]
        k = kdj.series[-1]
        r = rsi.series[-1]
        v = vol.series[-1]
        return (
            f"{symbol} 最新指标（{m.date}）：\n"
            f"- MACD：DIF={m.dif}，DEA={m.dea}，柱={m.macd}\n"
            f"- KDJ：K={k.k}，D={k.d}，J={k.j}\n"
            f"- RSI(14)：{r.rsi}\n"
            f"- 量能：量比={v.volume_ratio}，量价关系={v.relation}，收盘={v.close}"
        )

    def _get_signals(self, symbol: str, as_of: str | None = None) -> str:
        """扫单只股票在指定日期的所有战法信号（只扫一只，快）。"""
        if not symbol:
            return "缺少股票代码。"
        try:
            scan_date = date.fromisoformat(as_of) if as_of else date.today()
        except ValueError:
            return "日期格式无效，应为 YYYY-MM-DD。"
        try:
            signals: list = []
            for info in self._strategies.list_strategies():
                signals.extend(
                    self._strategies.scan_subset(info.name, scan_date, [symbol])
                )
            signals.sort(key=lambda s: s.score, reverse=True)
        except Exception as exc:  # noqa: BLE001 - 数据缺失等，降级为可读文本
            logger.warning("get_signals 失败（%s）：%s", symbol, exc)
            return f"无法获取 {symbol} 的信号数据（可能数据缺失）。"

        if not signals:
            return f"{symbol} 在 {scan_date} 未触发任何战法信号。"
        lines = [f"- {s.strategy} / {s.signal_type}（评分 {s.score:.0f}）" for s in signals]
        return f"{symbol} 在 {scan_date} 触发的信号：\n" + "\n".join(lines)

    def _list_strategies(self) -> str:
        """列出内置战法及说明。"""
        infos = self._strategies.list_strategies()
        if not infos:
            return "暂无可用策略。"
        lines = [f"- {i.name}（{i.label}）：{i.description}" for i in infos]
        return "平台内置战法策略：\n" + "\n".join(lines)

    def _retrieve_context(self, query: str) -> str:
        if not query:
            return "缺少检索关键词。"
        return self._rag.build_context(query) or "未检索到相关资料。"
