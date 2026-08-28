"""概览页服务：读离线快照 + 拼调度器实时执行状态。

职责边界：
    - 快照（各策略信号数/选择性/超额胜率 + 市场基线）由
      ``scripts/make_dashboard_snapshot.py`` 离线生成，本服务只读 JSON，
      避免概览页每次加载都触发全市场扫描（单日扫描约 1 分钟）。
    - 调度器执行状态（最近任务 / 最近一次全市场扫描）来自 SchedulerService，
      是实时数据。

降级原则：快照缺失 / 调度器连不上库都不报错，返回空字段，前端显示「暂无数据」，
保证「没有真实数据也能把页面跑起来」。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from schemas.dashboard import (
    DashboardBaseline,
    DashboardLastScan,
    DashboardOverview,
    DashboardStrategy,
)
from services.scheduler_service import SchedulerService

logger = logging.getLogger(__name__)


class DashboardService:
    """概览页聚合服务。"""

    def __init__(
        self,
        snapshot_path: Path,
        scheduler_service: SchedulerService,
    ) -> None:
        self._snapshot_path = snapshot_path
        self._scheduler = scheduler_service

    def overview(self) -> DashboardOverview:
        """返回概览页聚合数据（快照 + 调度器实时状态）。"""
        snap = self._load_snapshot()

        strategies = [DashboardStrategy(**s) for s in snap.get("strategies", [])]
        baselines = [DashboardBaseline(**b) for b in snap.get("baselines", [])]
        last_scan_raw = snap.get("last_scan")
        last_scan = (
            DashboardLastScan(**last_scan_raw) if last_scan_raw else None
        )

        recent_runs = self._safe_recent_runs()

        return DashboardOverview(
            as_of=snap.get("as_of"),
            strategies=strategies,
            baselines=baselines,
            last_scan=last_scan,
            recent_runs=recent_runs,
        )

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _load_snapshot(self) -> dict:
        """读快照 JSON，缺失 / 损坏返回空 dict（降级）。"""
        if not self._snapshot_path.exists():
            logger.warning("概览页快照缺失：%s", self._snapshot_path)
            return {}
        try:
            data = json.loads(self._snapshot_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("概览页快照解析失败：%s", exc)
            return {}

    def _safe_recent_runs(self):
        """查询最近调度执行记录；调度器仓储连不上时降级为空列表。"""
        try:
            return self._scheduler.list_runs(limit=10)
        except Exception as exc:  # noqa: BLE001 - 调度器仓储可能未连库，降级
            logger.warning("调度器执行记录查询失败：%s", exc)
            return []
