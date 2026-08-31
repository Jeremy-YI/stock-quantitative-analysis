"""LLM 服务（DeepSeek，OpenAI 兼容接口）。

职责：封装对 DeepSeek 的 HTTP 调用，把「结构化选股信号」翻译成自然语言解读。
只依赖 httpx（FastAPI 已带），不引入 openai SDK，保持轻量、可读。

一个 HTTP 调用长这样：
    POST https://api.deepseek.com/chat/completions
    { "model": "deepseek-chat", "messages": [{"role":"system",...},{"role":"user",...}] }
"""

from __future__ import annotations

import httpx

from strategies.signal import Signal

# 系统提示：告诉模型它的角色和输出要求
SYSTEM_PROMPT = (
    "你是 A 股短线策略助手。根据一只股票触发的选股信号，用简洁中文解释："
    "它触发了哪些信号、各是什么意思、大概该怎么操作、有什么风险。"
    "只基于给的信号解读，不要编造数据或价格。150 字以内。"
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

    def chat(self, system: str, user: str) -> str:
        """调 DeepSeek chat/completions，返回 assistant 回复文本。"""
        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,  # 低温度，解读更稳定、少跑偏
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        resp = httpx.post(url, json=payload, headers=headers, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def interpret(self, symbol: str, signals: list[Signal], context: str = "") -> str:
        """把一只票的信号列表翻译成一段自然语言解读。

        context 是检索增强（RAG）得到的背景资料，有则注入 prompt，
        让解读有依据（比如能说清「单针」到底是什么），而不是只复述信号名。
        """
        if not signals:
            return "该股票今日未触发任何战法信号，观望。"

        # 信号列表转成文字（给模型看的输入）
        lines = [f"- {s.strategy} / {s.signal_type}（评分 {s.score:.0f}）" for s in signals]
        user = f"股票代码 {symbol}，今日触发了以下信号：\n" + "\n".join(lines)
        if context:
            user += f"\n\n{context}"
        return self.chat(SYSTEM_PROMPT, user)
