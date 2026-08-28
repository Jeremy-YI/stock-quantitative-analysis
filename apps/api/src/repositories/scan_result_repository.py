"""策略扫描结果仓储。

与日线仓储同构：service 只依赖 ``ScanResultRepository`` 协议。
阶段 3 提供内存实现（默认，测试用）与 MySQL 实现（需 pymysql + MySQL 实例，
见 migrations/0002_strategy_scans.sql）。
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from strategies.signal import Signal


class ScanResultRepository(Protocol):
    """策略扫描结果仓储接口。"""

    def save(self, strategy: str, signals: list[Signal]) -> None:
        """落库一批信号（同策略同日同信号幂等）。"""
        ...

    def get_signals(
        self, strategy: str, start: date | None = None, end: date | None = None
    ) -> list[Signal]:
        """按策略 + 可选日期区间查询历史信号。"""
        ...


class InMemoryScanResultRepository:
    """内存实现：保存到进程内 dict，供测试与无 DB 场景使用。"""

    def __init__(self) -> None:
        self._store: dict[str, list[Signal]] = {}

    def save(self, strategy: str, signals: list[Signal]) -> None:
        key = strategy
        existing = {self._sig_key(s) for s in self._store.get(key, [])}
        merged = list(self._store.get(key, []))
        for s in signals:
            if self._sig_key(s) not in existing:
                merged.append(s)
                existing.add(self._sig_key(s))
        self._store[key] = merged

    def get_signals(
        self, strategy: str, start: date | None = None, end: date | None = None
    ) -> list[Signal]:
        signals = self._store.get(strategy, [])
        if start is not None:
            signals = [s for s in signals if s.triggered_at >= start]
        if end is not None:
            signals = [s for s in signals if s.triggered_at <= end]
        return sorted(signals, key=lambda s: (s.triggered_at, s.symbol, s.signal_type))

    @staticmethod
    def _sig_key(s: Signal) -> tuple:
        return (s.triggered_at, s.symbol, s.signal_type)


class MySqlScanResultRepository:
    """MySQL 实现（阶段 3 预留）。

    需要 ``pymysql`` 与可用的 MySQL 实例（见 docker-compose.yml 的 mysql 服务）。
    连接信息从环境变量 ``STOCK_MYSQL_*`` 读取；未配置时构造不报错，调用 save
    时才抛出带清晰提示的异常，避免本地跑测试强依赖数据库。
    """

    def __init__(self) -> None:
        self._conn = None

    def _connect(self):
        try:
            import pymysql  # 延迟导入，避免强依赖
        except ImportError as exc:  # pragma: no cover
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

    def save(self, strategy: str, signals: list[Signal]) -> None:  # pragma: no cover
        if self._conn is None:
            self._connect()
        sql = (
            "INSERT INTO strategy_scan_results "
            "(strategy, trade_date, symbol, signal_type, score, metrics_json) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE score=VALUES(score), metrics_json=VALUES(metrics_json)"
        )
        import json

        with self._conn.cursor() as cur:
            for s in signals:
                cur.execute(
                    sql,
                    (
                        strategy,
                        s.triggered_at.isoformat(),
                        s.symbol,
                        s.signal_type,
                        s.score,
                        json.dumps(s.metrics, ensure_ascii=False),
                    ),
                )
        self._conn.commit()

    def get_signals(
        self, strategy: str, start: date | None = None, end: date | None = None
    ) -> list[Signal]:  # pragma: no cover
        if self._conn is None:
            self._connect()
        import json

        where = ["strategy=%s"]
        params: list = [strategy]
        if start is not None:
            where.append("trade_date >= %s")
            params.append(start.isoformat())
        if end is not None:
            where.append("trade_date <= %s")
            params.append(end.isoformat())
        sql = (
            "SELECT symbol, signal_type, score, trade_date, metrics_json "
            "FROM strategy_scan_results WHERE "
            + " AND ".join(where)
            + " ORDER BY trade_date, symbol, signal_type"
        )
        from datetime import datetime

        out: list[Signal] = []
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            for symbol, signal_type, score, trade_date, metrics_json in cur.fetchall():
                out.append(
                    Signal(
                        symbol=symbol,
                        strategy=strategy,
                        signal_type=signal_type,
                        score=float(score),
                        triggered_at=(
                            trade_date.date()
                            if isinstance(trade_date, datetime)
                            else date.fromisoformat(str(trade_date))
                        ),
                        metrics=json.loads(metrics_json) if metrics_json else {},
                    )
                )
        return out
