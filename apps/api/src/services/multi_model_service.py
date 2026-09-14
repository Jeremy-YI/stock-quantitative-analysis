"""多模型并行研判（MoA）：两个不同模型并行分析，主模型汇总分歧。

按 ACP C3「混合专家 MoA」：Proposers（DeepSeek + Qwen）并行独立分析，
Aggregator（主模型）融合两者并指出分歧。
用 ThreadPoolExecutor 做并行（项目整体同步，不引 asyncio）。
副模型失败时降级为主模型单飞，保证可用性。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from services.llm_service import LlmService

logger = logging.getLogger(__name__)

# 聚合器系统提示：融合两个模型的分析并指出分歧
AGGREGATOR_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是一名 A 股短线策略分析师，负责融合两个模型对同一份数据的分析。\n\n"
    "# 任务\n"
    "下面是两个模型（模型 A、模型 B）对同一份数据的独立分析。请综合成一段最终解读：\n"
    "- 两者一致的部分直接采纳；\n"
    "- 两者矛盾/分歧的部分，明确指出分歧，并给出你的倾向判断。\n\n"
    "# 约束\n"
    "- 只基于两个模型的分析，不要编造新数据。\n"
    "- 面向散户，通俗中文，先给结论再给理由，250 字以内。"
)


class MultiModelService:
    """并行调两个模型分析，再用主模型汇总分歧。"""

    def __init__(self, primary: LlmService, secondary: LlmService) -> None:
        self._primary = primary  # DeepSeek（分析 + 聚合）
        self._secondary = secondary  # Qwen（第二分析视角）

    def analyze(self, system: str, user: str) -> str:
        """并行两个模型分析，主模型汇总。任一失败都优雅降级。"""
        with ThreadPoolExecutor(max_workers=2) as pool:
            fa = pool.submit(self._primary.chat, system, user)
            fb = pool.submit(self._secondary.chat, system, user)
            a = self._safe(fa)
            b = self._safe(fb)

        if a is None and b is None:
            return "AI 服务暂时不可用，请稍后再试。"
        if a is None:
            return b
        if b is None:
            return a

        # 聚合：主模型吃两个结果，输出融合 + 分歧
        agg_user = (
            "两个模型对同一份数据的分析如下，请综合并指出分歧：\n\n"
            f"【模型 A】{a}\n\n【模型 B】{b}"
        )
        agg = self._call_primary(AGGREGATOR_SYSTEM_PROMPT, agg_user)
        return agg if agg is not None else a

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    @staticmethod
    def _safe(future) -> str | None:
        """取 future 结果，失败返回 None。"""
        try:
            return future.result(timeout=60)
        except Exception as exc:  # noqa: BLE001 - 单个模型失败不影响整体
            logger.warning("模型调用失败：%s", exc)
            return None

    def _call_primary(self, system: str, user: str) -> str | None:
        try:
            return self._primary.chat(system, user)
        except Exception as exc:  # noqa: BLE001 - 聚合失败退回模型 A 结果
            logger.warning("聚合失败：%s", exc)
            return None
