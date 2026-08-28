"""因子研究服务：读离线快照 JSON，前端只读。

快照由 ``scripts/run_research.py --out data/research_snapshot.json`` 生成
（因子超额表 / 交叉矩阵 / regime 分层），本服务只读文件，不触发全市场计算。
缺失 / 损坏时返回空摘要（降级），与 DashboardService 同口径。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from schemas.research import ResearchSummary

logger = logging.getLogger(__name__)


class ResearchService:
    """因子研究快照读取服务。"""

    def __init__(self, snapshot_path: Path) -> None:
        self._snapshot_path = snapshot_path

    def summary(self) -> ResearchSummary:
        """返回因子研究快照汇总。"""
        data = self._load()
        if not data:
            return ResearchSummary()
        return ResearchSummary(**data)

    def _load(self) -> dict:
        if not self._snapshot_path.exists():
            logger.warning("因子研究快照缺失：%s", self._snapshot_path)
            return {}
        try:
            data = json.loads(self._snapshot_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("因子研究快照解析失败：%s", exc)
            return {}
