"""执行记录仓储。

与扫描/回测仓储同构：service 只依赖 ``RunRepository`` 协议。
阶段 5 提供内存实现（默认，测试用）与 MySQL 实现（表结构见
apps/api/migrations/0004_scheduler_runs.sql）。
"""

from __future__ import annotations

from typing import Protocol

from scheduler.models import RunRecord, RunStatus


class RunRepository(Protocol):
    """执行记录仓储接口。"""

    def save(self, record: RunRecord) -> None:
        """落库一条执行记录（同 run_id 幂等覆盖）。"""
        ...

    def get(self, run_id: str) -> RunRecord | None:
        """按 run_id 查询；不存在返回 None。"""
        ...

    def list(self, job: str | None = None, limit: int = 50) -> list[RunRecord]:
        """按时间倒序返回执行历史；job 非空时只查该任务。"""
        ...

    def latest(self, job: str) -> RunRecord | None:
        """某任务最近一次执行记录；无记录返回 None。"""
        ...


class InMemoryRunRepository:
    """内存实现：进程内 dict，供测试与无 DB 场景。"""

    def __init__(self) -> None:
        self._store: dict[str, RunRecord] = {}

    def save(self, record: RunRecord) -> None:
        self._store[record.run_id] = record

    def get(self, run_id: str) -> RunRecord | None:
        return self._store.get(run_id)

    def list(self, job: str | None = None, limit: int = 50) -> list[RunRecord]:
        records = list(self._store.values())
        if job is not None:
            records = [r for r in records if r.job_name == job]
        records.sort(key=lambda r: r.started_at, reverse=True)
        return records[:limit]

    def latest(self, job: str) -> RunRecord | None:
        matches = [r for r in self._store.values() if r.job_name == job]
        if not matches:
            return None
        return max(matches, key=lambda r: r.started_at)


class MySqlRunRepository:
    """MySQL 实现（需 pymysql + MySQL 实例）。

    连接信息从环境变量 ``STOCK_MYSQL_*`` 读取；未配置时构造不报错，调用 save
    才抛带清晰提示的异常，避免本地跑测试强依赖数据库。
    """

    def __init__(self) -> None:
        self._conn = None

    def _connect(self):  # pragma: no cover
        try:
            import pymysql  # 延迟导入，避免强依赖
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

    def save(self, record: RunRecord) -> None:  # pragma: no cover
        if self._conn is None:
            self._connect()
        sql = (
            "INSERT INTO scheduler_runs "
            "(run_id, job_name, trigger_type, status, started_at, finished_at, "
            " duration_seconds, progress, summary, error, attempt) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE status=VALUES(status), "
            " finished_at=VALUES(finished_at), duration_seconds=VALUES(duration_seconds), "
            " progress=VALUES(progress), summary=VALUES(summary), error=VALUES(error)"
        )
        with self._conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    record.run_id,
                    record.job_name,
                    record.trigger,
                    record.status.value,
                    record.started_at,
                    record.finished_at,
                    record.duration_seconds,
                    record.progress,
                    record.summary,
                    record.error,
                    record.attempt,
                ),
            )
        self._conn.commit()

    def get(self, run_id: str) -> RunRecord | None:  # pragma: no cover
        if self._conn is None:
            self._connect()
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT run_id, job_name, trigger_type, status, started_at, "
                "finished_at, duration_seconds, progress, summary, error, attempt "
                "FROM scheduler_runs WHERE run_id=%s",
                (run_id,),
            )
            row = cur.fetchone()
        return self._row_to_record(row)

    def list(self, job: str | None = None, limit: int = 50) -> list[RunRecord]:  # pragma: no cover
        if self._conn is None:
            self._connect()
        where = ""
        params: list = []
        if job is not None:
            where = "WHERE job_name=%s"
            params.append(job)
        params.append(int(limit))
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT run_id, job_name, trigger_type, status, started_at, "
                "finished_at, duration_seconds, progress, summary, error, attempt "
                f"FROM scheduler_runs {where} ORDER BY started_at DESC LIMIT %s",
                params,
            )
            rows = cur.fetchall()
        return [r for r in (self._row_to_record(row) for row in rows) if r]

    def latest(self, job: str) -> RunRecord | None:  # pragma: no cover
        records = self.list(job=job, limit=1)
        return records[0] if records else None

    @staticmethod
    def _row_to_record(row) -> RunRecord | None:
        if row is None:
            return None
        (
            run_id, job_name, trigger_type, status, started_at,
            finished_at, duration_seconds, progress, summary, error, attempt,
        ) = row
        return RunRecord(
            run_id=run_id,
            job_name=job_name,
            trigger=trigger_type,
            status=RunStatus(status),
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration_seconds,
            progress=progress,
            summary=summary or "",
            error=error or "",
            attempt=attempt or 0,
        )
