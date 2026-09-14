"""LLM 服务（DeepSeek，OpenAI 兼容接口）。

职责：封装对 DeepSeek 的 HTTP 调用，把「结构化选股信号」翻译成自然语言解读，
并为 Agent 提供带工具调用（Function Calling）能力的底层接口。
只依赖 httpx（FastAPI 已带），不引入 openai SDK，保持轻量、可读。

一个 HTTP 调用长这样：
    POST https://api.deepseek.com/chat/completions
    { "model": "deepseek-chat", "messages": [{"role":"system",...},{"role":"user",...}],
      "tools": [{"type":"function","function":{"name":...,"description":...,"parameters":...}}] }
"""

from __future__ import annotations

import logging

import httpx

from strategies.signal import Signal

logger = logging.getLogger(__name__)

# 解读用系统提示（interpret 流程：信号列表 → 人话解读）
SYSTEM_PROMPT = (
    "# 角色\n"
    "你是一名 A 股短线策略分析师，负责把技术面选股信号翻译成个人投资者听得懂、能执行的解读。\n\n"
    "# 输入\n"
    "你会收到两部分，用【】分隔：\n"
    "【信号】一只股票今日触发的信号列表，每行格式为「策略名 / 信号子类型（评分）」，评分越大优先级越高。\n"
    "【背景】可选，是从知识库检索到的资料（策略定义、当日财经消息、事件日历）。有则优先依据，没有则按常识解释。\n\n"
    "# 输出（严格按以下三段，用 ### 开头）\n"
    "### 信号含义\n"
    "逐个说明每个信号代表什么（有背景时依据背景，别只复述信号名）。\n"
    "### 操作参考\n"
    "给出方向性建议（关注 / 试探 / 加仓 / 回避），并说明一句依据。\n"
    "### 风险提示\n"
    "指出 1-2 个主要风险点。\n\n"
    "# 硬性约束\n"
    "- 只基于给定的信号和背景解读，严禁编造价格、涨跌幅、成交量等具体数字。\n"
    "- 背景没提的信息，就写「资料未提及」，不要脑补。\n"
    "- 面向散户，用词通俗，少堆术语。\n"
    "- 全文 200 字以内。"
)


class LlmService:
    """DeepSeek 调用封装。"""

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model

    @property
    def enabled(self) -> bool:
        """是否配置了 API key（没配则前端禁用 AI 功能）。"""
        return bool(self._api_key)

    def _post(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
    ) -> dict:
        """POST chat/completions，返回完整响应 JSON。"""
        payload: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
        headers = {"Authorization": f"Bearer {self._api_key}"}
        resp = httpx.post(
            f"{self._base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    def chat(self, system: str, user: str) -> str:
        """单轮对话：返回 assistant 回复文本（interpret 用）。"""
        data = self._post(
            [{"role": "system", "content": system}, {"role": "user", "content": user}]
        )
        return data["choices"][0]["message"]["content"].strip()

    def chat_message(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> dict:
        """带工具支持的对话：返回 choices[0].message（含 content / tool_calls）。

        Agent 循环据此判断：有 tool_calls 则执行工具并回传，否则拿 content 作答。
        """
        data = self._post(messages, tools=tools)
        return data["choices"][0]["message"]

    def interpret(self, symbol: str, signals: list[Signal], context: str = "") -> str:
        """把一只票的信号列表翻译成一段自然语言解读（带 RAG 背景）。"""
        if not signals:
            return "该股票今日未触发任何战法信号，观望。"

        lines = [f"- {s.strategy} / {s.signal_type}（评分 {s.score:.0f}）" for s in signals]
        user = f"【信号】\n股票代码 {symbol}，今日触发了以下信号：\n" + "\n".join(lines)
        if context:
            user += f"\n\n【背景】\n{context}"
        try:
            return self.chat(SYSTEM_PROMPT, user)
        except Exception as exc:  # noqa: BLE001 - LLM 挂了降级为可读提示，不 500
            logger.warning("interpret 调用 LLM 失败（%s）：%s", symbol, exc)
            return "AI 解读暂时不可用，请稍后再试。"
