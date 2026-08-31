"""检索增强（RAG）服务测试。

重点验证「真检索」而非摆设：
  - 用信号名查询，能检索回对应战法的定义
  - 用主题词查询，能检索回相关财经消息
  - 空语料 / 无相关时优雅降级
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from services.rag_service import RagService, _bigrams


@dataclass
class FakeStrategyInfo:
    label: str
    description: str


STRATEGY_INFOS = [
    FakeStrategyInfo("单针", "单针下30：短期随机指标≤30且长期≥80，长期强势中的急跌回调"),
    FakeStrategyInfo("双底", "双底：价格二次探底后回升，突破颈线确认"),
]

NEWS = {
    "date": "2026-08-30",
    "items": [
        {
            "title": "金价暴跌失守4500",
            "impact": "改变定价",
            "outlook": "实际利率+美元双杀",
            "detail": "纽约金单日跌3.43%，跌破200日均线",
            "topics": ["黄金", "美联储"],
        },
    ],
}

EVENTS = {
    "events": [
        {
            "name": "美联储 FOMC 利率决议",
            "date": "2026-09-16",
            "type": "央行会议",
            "importance": "高",
            "description": "美联储利率决议，全球资产定价锚",
        },
    ],
}


@pytest.fixture()
def rag(tmp_path):
    news = tmp_path / "news.json"
    events = tmp_path / "events.json"
    news.write_text(json.dumps(NEWS, ensure_ascii=False), encoding="utf-8")
    events.write_text(json.dumps(EVENTS, ensure_ascii=False), encoding="utf-8")
    return RagService(news_path=str(news), events_path=str(events)).build(STRATEGY_INFOS)


def test_bigrams_tokens():
    """中文按字符二元组切，英文按词保留。"""
    tokens = _bigrams("单针下30")
    assert "单针" in tokens
    assert "针下" in tokens
    assert "macd" in _bigrams("MACD 金叉")


def test_build_corpus(rag):
    # 2 策略 + 1 消息 + 1 事件
    assert rag.size() == 4


def test_retrieve_strategy_by_signal(rag):
    chunks = rag.retrieve("单针 pin30", top_k=2)
    assert chunks, "用信号名应能检索到战法定义"
    assert any(c.source == "strategy" and c.title == "单针" for c in chunks)


def test_retrieve_news_by_topic(rag):
    chunks = rag.retrieve("黄金 金价 暴跌", top_k=3)
    assert any(c.source == "news" and "金价暴跌" in c.title for c in chunks)


def test_retrieve_returns_ordered_relevant(rag):
    chunks = rag.retrieve("美联储 利率 决议", top_k=3)
    assert chunks
    # 事件「FOMC」应排最前
    assert chunks[0].source == "event" and "FOMC" in chunks[0].title


def test_build_context_injects_knowledge(rag):
    ctx = rag.build_context("单针 pin30")
    assert "单针下30" in ctx  # 检索到了战法定义并注入


def test_empty_corpus_degrades():
    empty = RagService(news_path="/nonexistent/news.json", events_path="/nonexistent/e.json")
    assert empty.size() == 0
    assert empty.retrieve("单针") == []
    assert empty.build_context("单针") == ""
