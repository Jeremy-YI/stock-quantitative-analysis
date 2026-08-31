"""轻量检索增强（RAG）：给 AI 解读提供「背景知识」。

设计取舍（诚实版，回应「RAG 是不是为了用而用」）：
  - 检索用**字符二元组 BM25**，零外部依赖（不装 jieba / 向量库 / embedding 模型）。
  - 语料 = 策略定义（7 个战法是什么）+ 当日财经消息 + 事件日历。
  - 用途：AI 解读一只票时，先检索和「这只票触发的信号 / 相关主题」最相关的知识，
    注入 prompt，让解读有依据、不凭空编。

为什么不用向量 RAG：
  当前语料只有几十条，BM25 已经够准；向量检索需要 embedding 模型或 API（本地重、
  要额外密钥），对这个小语料是「为了用而用」。若以后语料涨到几千条，把 retriever
  换成 embedding + 向量库即可，接口不变（RagService.retrieve 是唯一入口）。

这个服务是「真检索 + 真注入」，不是摆设：
  - AI 解读之前，先 retrieve(query) 拿到最相关的知识块
  - 注入 prompt 后，模型能说出「单针 = 长期强势中的急跌回调」这种有依据的话，
    而不是只复述信号名。
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_NEWS_PATH = _REPO_ROOT / "data" / "news.json"
_EVENTS_PATH = _REPO_ROOT / "data" / "events.json"


@dataclass
class RagChunk:
    """一条可被检索的知识块。"""

    source: str      # strategy / news / event
    title: str
    text: str


def _bigrams(text: str) -> list[str]:
    """中文字符二元组（无分词依赖的分词近似）。

    英文单词保留原样；中文按相邻两字切。对几十条语料的检索足够。
    """
    tokens: list[str] = []
    for word in re.findall(r"[A-Za-z0-9_]+", text):
        tokens.append(word.lower())
    chinese = re.sub(r"[A-Za-z0-9_\s]+", "", text)
    tokens.extend(chinese[i : i + 2] for i in range(len(chinese) - 1))
    return tokens


def _bm25_score(query_terms: list[str], doc_terms: list[str], doc_count: int, doc_lengths: list[int], term_doc_freq: dict[str, int], avg_len: float) -> float:
    """标准 BM25 打分（k1=1.5, b=0.75），空文档防御已在外层处理。"""
    k1, b = 1.5, 0.75
    doc_len = len(doc_terms) or 1
    score = 0.0
    tf: dict[str, int] = {}
    for t in doc_terms:
        tf[t] = tf.get(t, 0) + 1
    for term in query_terms:
        if term not in term_doc_freq:
            continue
        n = term_doc_freq[term]
        idf = math.log(1 + (doc_count - n + 0.5) / (n + 0.5))
        f = tf.get(term, 0)
        score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * doc_len / avg_len))
    return score


class RagService:
    """检索增强服务：构建语料 + BM25 检索 + 拼 prompt 上下文。"""

    def __init__(self, news_path: str | None = None, events_path: str | None = None) -> None:
        self._news_path = Path(news_path) if news_path else _NEWS_PATH
        self._events_path = Path(events_path) if events_path else _EVENTS_PATH
        self._chunks: list[RagChunk] = []
        self._indexed = False

    # ------------------------------------------------------------------
    # 语料构建
    # ------------------------------------------------------------------
    def build(self, strategy_infos: list | None = None) -> "RagService":
        """重建语料：策略定义 + 消息 + 事件。strategy_infos 来自 StrategyService.list_strategies()。"""
        chunks: list[RagChunk] = []

        for info in strategy_infos or []:
            chunks.append(
                RagChunk(
                    source="strategy",
                    title=info.label,
                    text=f"战法「{info.label}」：{info.description}",
                )
            )

        news = self._load_json(self._news_path)
        for item in news.get("items", []):
            topics = "、".join(item.get("topics", []))
            chunks.append(
                RagChunk(
                    source="news",
                    title=item.get("title", ""),
                    text=(
                        f"财经消息「{item.get('title', '')}」（影响：{item.get('impact', '')}，"
                        f"主题：{topics}）。{item.get('detail', '')} {item.get('outlook', '')}"
                    ),
                )
            )

        events = self._load_json(self._events_path)
        for ev in events.get("events", []):
            chunks.append(
                RagChunk(
                    source="event",
                    title=ev.get("name", ""),
                    text=f"事件「{ev.get('name', '')}」（{ev.get('date', '')}，{ev.get('type', '')}，"
                    f"重要度{ev.get('importance', '')}）。{ev.get('description', '')}",
                )
            )

        self._chunks = chunks
        self._indexed = False
        return self

    def size(self) -> int:
        return len(self._chunks)

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------
    def retrieve(self, query: str, top_k: int = 3) -> list[RagChunk]:
        """按 BM25 返回最相关的 top_k 个知识块。"""
        if not self._chunks:
            return []
        query_terms = _bigrams(query)
        if not query_terms:
            return []

        doc_terms = [_bigrams(c.text) for c in self._chunks]
        doc_lengths = [len(t) for t in doc_terms]
        avg_len = (sum(doc_lengths) / len(doc_lengths)) or 1.0

        term_doc_freq: dict[str, int] = {}
        for terms in doc_terms:
            for t in set(terms):
                term_doc_freq[t] = term_doc_freq.get(t, 0) + 1

        scored = [
            (_bm25_score(query_terms, doc_terms[i], len(self._chunks), doc_lengths, term_doc_freq, avg_len), self._chunks[i])
            for i in range(len(self._chunks))
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored if _ > 0][:top_k]

    def build_context(self, query: str, top_k: int = 3) -> str:
        """检索并拼成一段给 LLM 的背景上下文（markdown 列表）。"""
        chunks = self.retrieve(query, top_k)
        if not chunks:
            return ""
        lines = ["以下是相关背景资料（检索得到，供你参考，不要编造资料里没有的数据）："]
        for c in chunks:
            lines.append(f"- [{c.source}] {c.title}：{c.text}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    @staticmethod
    def _load_json(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
