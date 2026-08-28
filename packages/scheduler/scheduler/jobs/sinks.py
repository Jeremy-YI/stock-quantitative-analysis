"""选股信号落库 + 查询 sink。

调度器的「每日收盘全市场扫描」任务把扫出的 Signal 落到 strategy_scan_results
表（与 apps/api/migrations/0002_strategy_scans.sql 同表结构）。为避免与
apps/api 的仓储反向依赖，本包自带一份薄实现（SQL 与 migration 对齐）。
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from strategies.signal import Signal


class ScanSink(Protocol):
    """信号落库 / 查询接口。"""

    def save(self, strategy: str, signals: list[Signal]) -> int:
        """落库一批信号（同策略同日同标的同信号幂等），返回写入行数。"""
        ...

    def get_signals(
        self, strategy: str, start: date | None = None, end: date | None = None
    ) -> list[Signal]:
        """按策略 + 可选日期区间查询历史信号（触发日升序）。"""
        ...


class InMemoryScanSink:
    """内存实现：进程内 dict，供测试。"""

    def __init__(self) -> None:
        self._store: dict[str, list[Signal]] = {}

    def save(self, strategy: str, signals: list[Signal]) -> int:
        existing = {
            (s.triggered_at, s.symbol, s.signal_type)
            for s in self._store.get(strategy, [])
        }
        added = 0
        for s in signals:
            key = (s.triggered_at, s.symbol, s.signal_type)
            if key not in existing:
                self._store.setdefault(strategy, []).append(s)
                existing.add(key)
                added += 1
        return added

    def get_signals(
        self, strategy: str, start: date | None = None, end: date | None = None
    ) -> list[Signal]:
        signals = self._store.get(strategy, [])
        if start is not None:
            signals = [s for s in signals if s.triggered_at >= start]
        if end is not None:
            signals = [s for s in signals if s.triggered_at <= end]
        return sorted(signals, key=lambda s: (s.triggered_at, s.symbol, s.signal_type))


class MySqlScanSink:
    """MySQL 实现（需 pymysql，连接信息从 STOCK_MYSQL_* 读）。"""

    def __init__(self) -> None:
        self._conn = None

    def _connect(self):  # pragma: no cover
        try:
            import pymysql
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

    def save(self, strategy: str, signals: list[Signal]) -> int:  # pragma: no cover
        if self._conn is None:
            self._connect()
        import json

        sql = (
            "INSERT INTO strategy_scan_results "
            "(strategy, trade_date, symbol, signal_type, score, metrics_json) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE score=VALUES(score), metrics_json=VALUES(metrics_json)"
        )
        n = 0
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
                n += 1
        self._conn.commit()
        return n

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
