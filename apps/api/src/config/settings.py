"""应用配置。

环境变量优先级：环境变量 > .env 文件 > 默认值。
命名约定：环境变量用前缀 `STOCK_` + 字段名大写，例如 `STOCK_HSJDAY_ROOT`。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="STOCK_",
        extra="ignore",
    )

    # 通达信 hsjday 日线数据根目录
    hsjday_root: str = "~/Desktop/每日复盘/hsjday"
    # 允许跨域的前端来源
    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def hsjday_path(self) -> Path:
        """展开 `~` 并返回 Path，供数据源使用。"""
        return Path(self.hsjday_root).expanduser()


@lru_cache
def get_settings() -> Settings:
    """单例配置（进程内只解析一次 .env）。"""
    return Settings()
