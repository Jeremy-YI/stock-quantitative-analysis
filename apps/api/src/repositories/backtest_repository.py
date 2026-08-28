"""回测任务仓储。

与扫描结果仓储同构：service 只依赖 ``BacktestRunRepository`` 协议。
阶段 4 提供内存实现（默认，测试用）与 MySQL 实现（见
migrations/0003_backtest_runs.sql）。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from schemas.backtest import BacktestRunBody


class BacktestRunRepository(Protocol):
    """回测任务仓储接口。"""

    def save(self, run: BacktestRunBody) -> None:
        """保存一次回测任务（含报告 JSON）。"""
        ...

    def get(self, run_id: str) -> BacktestRunBody | None:
        """按 id 查询回测任务，不存在返回 None。"""
        ...


class InMemoryBacktestRunRepository:
    """内存实现：进程内 dict。"""

    def __init__(self) -> None:
        self._store: dict[str, BacktestRunBody] = {}

    def save(self, run: BacktestRunBody) -> None:
        self._store[run.run_id] = run

    def get(self, run_id: str) -> BacktestRunBody | None:
        return self._store.get(run_id)


class MySqlBacktestRunRepository:
    """MySQL 实现（阶段 4 预留，需 pymysql + MySQL 实例）。

    未配置连接时构造不报错，调用 save 才抛带清晰提示的异常，避免本地测试
    强依赖数据库。
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

    def save(self, run: BacktestRunBody) -> None:  # pragma: no cover
        if self._conn is None:
            self._connect()
        import json

        sql = (
            "INSERT INTO backtest_runs "
            "(id, strategy, start_date, end_date, mode, hold_days, result_json) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE result_json=VALUES(result_json)"
        )
        with self._conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    run.run_id,
                    run.strategy,
                    run.start.isoformat(),
                    run.end.isoformat(),
                    run.mode,
                    ",".join(map(str, run.report.verification.hold_days)),
                    json.dumps(run.report.model_dump(mode="json"), ensure_ascii=False),
                ),
            )
        self._conn.commit()

    def get(self, run_id: str) -> BacktestRunBody | None:  # pragma: no cover
        if self._conn is None:
            self._connect()
        import json

        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, strategy, start_date, end_date, mode, result_json "
                "FROM backtest_runs WHERE id=%s",
                (run_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None

        from backtest.models import BacktestReport

        _id, strategy, start_date, end_date, mode, result_json = row
        report = BacktestReport.model_validate(json.loads(result_json))
        return BacktestRunBody(
            run_id=_id,
            strategy=strategy,
            start=start_date.date() if hasattr(start_date, "date") else start_date,
            end=end_date.date() if hasattr(end_date, "date") else end_date,
            mode=mode,
            report=report,
        )
