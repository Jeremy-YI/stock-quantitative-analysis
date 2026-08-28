"""应用配置。

环境变量优先级：环境变量 > .env 文件 > 默认值。
命名约定：环境变量用前缀 `STOCK_` + 字段名大写，例如 `STOCK_HSJDAY_ROOT`。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from datasource.tdx import DEFAULT_HSJDAY_ROOT


class Settings(BaseSettings):
    """全局配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="STOCK_",
        extra="ignore",
    )

    # 通达信 hsjday 日线数据根目录
    hsjday_root: str = str(DEFAULT_HSJDAY_ROOT)
    # 允许跨域的前端来源
    cors_origins: list[str] = ["http://localhost:3000"]
    # 调度器：报告输出目录（FileNotifier 写 Markdown 到这里）
    scheduler_report_dir: str = "~/Desktop/stock-platform/reports"
    # 调度器：飞书 webhook URL（WebhookNotifier，从 .env 读，绝不硬编码）
    feishu_webhook_url: str = ""
    # 概览页快照路径（make_dashboard_snapshot.py 离线生成，Dashboard 只读）
    # 留空 = 用仓库内默认 data/dashboard_snapshot.json（相对仓库根目录）
    dashboard_snapshot_path: str = ""
    # 因子研究快照路径（run_research.py 离线生成，Research 只读）
    research_snapshot_path: str = ""

    @property
    def hsjday_path(self) -> Path:
        """展开 `~` 并返回 Path，供数据源使用。"""
        return Path(self.hsjday_root).expanduser()

    @property
    def dashboard_snapshot_path_resolved(self) -> Path:
        """解析概览页快照的绝对路径。

        环境变量给了相对路径则相对当前工作目录；没给就用仓库内默认
        ``<仓库根>/data/dashboard_snapshot.json``（本地与容器内都成立）。
        """
        if self.dashboard_snapshot_path:
            return Path(self.dashboard_snapshot_path).expanduser()
        # config/settings.py 位于 apps/api/src/config/，仓库根 = 向上 4 层
        repo_root = Path(__file__).resolve().parents[4]
        return repo_root / "data" / "dashboard_snapshot.json"

    @property
    def research_snapshot_path_resolved(self) -> Path:
        """解析因子研究快照的绝对路径（默认 ``<仓库根>/data/research_snapshot.json``）。"""
        if self.research_snapshot_path:
            return Path(self.research_snapshot_path).expanduser()
        repo_root = Path(__file__).resolve().parents[4]
        return repo_root / "data" / "research_snapshot.json"


@lru_cache
def get_settings() -> Settings:
    """单例配置（进程内只解析一次 .env）。"""
    return Settings()
