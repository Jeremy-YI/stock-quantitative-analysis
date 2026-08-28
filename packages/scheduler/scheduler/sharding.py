"""分片执行 + 断点续跑状态。

长任务（全市场扫描 ~69s、回测几十分钟）把标的宇宙分成若干片，每片独立记录
「是否完成」。任务被中断（超时 / 异常）后，下次运行时跳过已完成的分片，
只跑未完成的片。

分片标识 = ``(job_name, batch_key, shard_id)``，batch_key 通常是交易日（如
"2026-08-27"），shard_id 是分片序号（从 0 起）。
"""

from __future__ import annotations

from typing import Protocol


class ShardTracker(Protocol):
    """分片完成状态追踪接口。"""

    def is_done(self, job_name: str, batch_key: str, shard_id: int) -> bool:
        """该片是否已完成。"""
        ...

    def mark_done(self, job_name: str, batch_key: str, shard_id: int) -> None:
        """标记该片已完成。"""
        ...

    def done_shards(self, job_name: str, batch_key: str) -> set[int]:
        """返回该批次已完成的分片序号集合。"""
        ...


class InMemoryShardTracker:
    """内存实现：进程内 dict，供测试与单进程运行。"""

    def __init__(self) -> None:
        self._done: dict[tuple[str, str], set[int]] = {}

    def is_done(self, job_name: str, batch_key: str, shard_id: int) -> bool:
        return shard_id in self._done.get((job_name, batch_key), set())

    def mark_done(self, job_name: str, batch_key: str, shard_id: int) -> None:
        self._done.setdefault((job_name, batch_key), set()).add(shard_id)

    def done_shards(self, job_name: str, batch_key: str) -> set[int]:
        return set(self._done.get((job_name, batch_key), set()))


class MySqlShardTracker:
    """MySQL 实现（表见 migrations/0004_scheduler_runs.sql）。

    未配置连接时构造不报错，调用时才抛带清晰提示的异常，避免测试强依赖 DB。
    """

    def __init__(self) -> None:
        self._conn = None

    def _connect(self):  # pragma: no cover
        try:
            import pymysql  # 延迟导入
        except ImportError as exc:
            raise RuntimeError("pymysql 未安装：pip install pymysql") from exc

        import os

        self._conn = pymysql.connect(
            host=os.environ.get("STOCK_MYSQL_HOST", "localhost"),
            port=int(os.environ.get("STOCK_MYSQL_PORT", "3306")),
            user=os.environ.get("STOCK_MYSQL_USER", "stock"),
            password=os.environ.get("STOCK_MYSQL_PASSWORD", "stock"),
            database=os.environ.get("STOCK_MYSQL_DB", "stock_platform"),
            charset="utf8mb4",
        )

    def is_done(self, job_name: str, batch_key: str, shard_id: int) -> bool:  # pragma: no cover
        if self._conn is None:
            self._connect()
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM scheduler_shards "
                "WHERE job_name=%s AND batch_key=%s AND shard_id=%s",
                (job_name, batch_key, shard_id),
            )
            return cur.fetchone() is not None

    def mark_done(self, job_name: str, batch_key: str, shard_id: int) -> None:  # pragma: no cover
        if self._conn is None:
            self._connect()
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO scheduler_shards "
                "(job_name, batch_key, shard_id) VALUES (%s, %s, %s)",
                (job_name, batch_key, shard_id),
            )
        self._conn.commit()

    def done_shards(self, job_name: str, batch_key: str) -> set[int]:  # pragma: no cover
        if self._conn is None:
            self._connect()
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT shard_id FROM scheduler_shards "
                "WHERE job_name=%s AND batch_key=%s",
                (job_name, batch_key),
            )
            return {row[0] for row in cur.fetchall()}
