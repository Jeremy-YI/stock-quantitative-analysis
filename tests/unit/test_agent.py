"""Agent 服务单测（ReAct 循环 + 工具执行，用 fake LLM / fake 指标，不碰真实 API/数据）。"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from schemas.indicator import (
    KdjBody,
    KdjPoint,
    MacdBody,
    MacdPoint,
    RsiBody,
    RsiPoint,
    VolumeBody,
    VolumePoint,
)
from services.agent_service import AgentService, TOOLS
from services.multi_model_service import MultiModelService


class FakeLlm:
    """按脚本返回 message，记录收到的 messages 供断言。"""

    def __init__(self, script: list[dict]) -> None:
        self._script = list(script)
        self.calls: list[list[dict]] = []

    def chat_message(self, messages, tools=None):
        self.calls.append(messages)
        return self._script.pop(0)


class FakeIndicators:
    def get_macd(self, symbol, start=None, end=None, limit=None):
        return MacdBody(
            symbol=symbol,
            series=[MacdPoint(date=date(2026, 9, 1), close=10.0, dif=0.1, dea=0.05, macd=0.05)],
        )

    def get_kdj(self, symbol, start=None, end=None, limit=None):
        return KdjBody(
            symbol=symbol,
            series=[KdjPoint(date=date(2026, 9, 1), close=10.0, k=45.0, d=40.0, j=55.0)],
        )

    def get_rsi(self, symbol, start=None, end=None, limit=None):
        return RsiBody(
            symbol=symbol,
            series=[RsiPoint(date=date(2026, 9, 1), close=10.0, rsi=58.0)],
        )

    def get_volume(self, symbol, start=None, end=None, limit=None):
        return VolumeBody(
            symbol=symbol,
            series=[
                VolumePoint(
                    date=date(2026, 9, 1),
                    close=10.0,
                    volume=1000,
                    mavol1=900.0,
                    mavol2=800.0,
                    volume_ratio=1.2,
                    relation="价升量增",
                )
            ],
        )


class FakeRag:
    def build_context(self, query, top_k=3):
        return "战法「单针下30」：长期强势中的急跌回调。"


class FakeStrategy:
    """返回固定策略元数据 + 单只票信号。"""

    def list_strategies(self):
        return [
            SimpleNamespace(
                name="b1b2b3",
                label="KDJ量价",
                description="B1超卖、B2确认、B3洗盘",
            )
        ]

    def scan_subset(self, name, as_of, symbols):
        if name == "b1b2b3":
            return [
                SimpleNamespace(strategy="b1b2b3", signal_type="b2", score=78.0)
            ]
        return []


def _make_agent(llm, multi=None):
    return AgentService(llm, FakeIndicators(), FakeRag(), FakeStrategy(), multi=multi)


def _tool_call(name: str, args: str) -> dict:
    return {
        "id": "c1",
        "type": "function",
        "function": {"name": name, "arguments": args},
    }


def test_agent_calls_tool_then_returns_answer():
    script = [
        {"role": "assistant", "content": None, "tool_calls": [_tool_call("get_indicators", '{"symbol": "600519"}')]},
        {"role": "assistant", "content": "MACD 多头，可关注。"},
    ]
    llm = FakeLlm(script)
    agent = _make_agent(llm)

    answer = agent.run("600519", "走势怎么样？")

    assert answer == "MACD 多头，可关注。"
    assert llm.calls[1][-1]["role"] == "tool"
    assert "DIF=0.1" in llm.calls[1][-1]["content"]


def test_agent_no_tools_returns_direct():
    llm = FakeLlm([{"role": "assistant", "content": "直接回答。"}])
    agent = _make_agent(llm)

    assert agent.run("600519", "你好") == "直接回答。"


def test_retrieve_context_tool():
    script = [
        {"role": "assistant", "content": None, "tool_calls": [_tool_call("retrieve_context", '{"query": "单针"}')]},
        {"role": "assistant", "content": "依据资料作答。"},
    ]
    llm = FakeLlm(script)
    agent = _make_agent(llm)

    answer = agent.run("600519", "单针是什么意思")

    assert answer == "依据资料作答。"
    assert "单针下30" in llm.calls[1][-1]["content"]


def test_get_signals_tool():
    script = [
        {"role": "assistant", "content": None, "tool_calls": [_tool_call("get_signals", '{"symbol": "600519", "as_of": "2026-09-01"}')]},
        {"role": "assistant", "content": "该股触发 b2 信号。"},
    ]
    llm = FakeLlm(script)
    agent = _make_agent(llm)

    answer = agent.run("600519", "触发了什么信号")

    assert answer == "该股触发 b2 信号。"
    assert "b1b2b3 / b2" in llm.calls[1][-1]["content"]


def test_list_strategies_tool():
    script = [
        {"role": "assistant", "content": None, "tool_calls": [_tool_call("list_strategies", "{}")]},
        {"role": "assistant", "content": "有 b1b2b3 等战法。"},
    ]
    llm = FakeLlm(script)
    agent = _make_agent(llm)

    answer = agent.run("600519", "有哪些策略")

    assert answer == "有 b1b2b3 等战法。"
    assert "KDJ量价" in llm.calls[1][-1]["content"]


def test_agent_llm_failure_degrades_gracefully():
    class BoomLlm:
        def chat_message(self, messages, tools=None):
            raise RuntimeError("boom")

    agent = _make_agent(BoomLlm())
    assert agent.run("600519", "走势") == "AI 服务暂时不可用，请稍后再试。"


def test_tools_schema_names():
    names = {t["function"]["name"] for t in TOOLS}
    assert names == {"get_indicators", "get_signals", "list_strategies", "retrieve_context"}


class FakeChat:
    """单轮 chat 的 fake：按队列返回，记录调用。"""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def chat(self, system, user):
        self.calls.append((system, user))
        return self._replies.pop(0)


def test_multi_model_parallel_and_aggregate():
    primary = FakeChat(["主模型分析", "聚合后的最终解读"])
    secondary = FakeChat(["副模型分析"])
    multi = MultiModelService(primary, secondary)

    result = multi.analyze("sys", "usr")

    assert result == "聚合后的最终解读"
    assert len(primary.calls) == 2
    agg_user = primary.calls[1][1]
    assert "主模型分析" in agg_user and "副模型分析" in agg_user


def test_multi_model_secondary_fails_degrades():
    class Boom:
        def chat(self, system, user):
            raise RuntimeError("boom")

    primary = FakeChat(["主模型分析"])
    multi = MultiModelService(primary, Boom())

    assert multi.analyze("sys", "usr") == "主模型分析"


def test_agent_uses_multi_model_for_final_answer():
    script = [
        {"role": "assistant", "content": None, "tool_calls": [_tool_call("get_indicators", '{"symbol": "600519"}')]},
        {"role": "assistant", "content": "单模型答案（多模型模式下会被忽略）"},
    ]
    llm = FakeLlm(script)
    primary = FakeChat(["主模型分析", "聚合后的最终解读"])
    secondary = FakeChat(["副模型分析"])
    multi = MultiModelService(primary, secondary)
    agent = _make_agent(llm, multi=multi)

    answer = agent.run("600519", "走势怎么样？")

    assert answer == "聚合后的最终解读"
    assert "DIF=0.1" in primary.calls[0][1]
