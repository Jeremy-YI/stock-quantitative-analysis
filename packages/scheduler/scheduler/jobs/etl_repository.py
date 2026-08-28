"""盘后 ETL 落库仓储。

把 AKShare 拉到的板块资金流 / ETF 资金流 / ST 名单快照落 MySQL（表结构见
apps/api/migrations/0004_scheduler_runs.sql）。与扫描/回测/执行仓储同构：
service 只依赖 ``EtlRepository`` 协议，内存实现供测试，MySQL 实现供生产。
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd


class EtlRepository(Protocol):
    """盘后 ETL 落库接口。"""

    def save_sector_flow(self, trade_date: date, df: pd.DataFrame) -> int:
        """落库板块资金流，返回写入行数。"""
        ...

    def save_etf_flow(self, trade_date: date, df: pd.DataFrame) -> int:
        """落库 ETF 资金流，返回写入行数。"""
        ...

    def save_st_snapshot(self, trade_date: date, df: pd.DataFrame) -> int:
        """落库 ST 名单快照（覆盖式，返回写入行数）。"""
        ...


class InMemoryEtlRepository:
    """内存实现：进程内 dict，供测试。"""

    def __init__(self) -> None:
        self.sector_flow: dict[str, pd.DataFrame] = {}
        self.etf_flow: dict[str, pd.DataFrame] = {}
        self.st_snapshot: dict[str, pd.DataFrame] = {}

    def save_sector_flow(self, trade_date: date, df: pd.DataFrame) -> int:
        self.sector_flow[trade_date.isoformat()] = df
        return len(df)

    def save_etf_flow(self, trade_date: date, df: pd.DataFrame) -> int:
        self.etf_flow[trade_date.isoformat()] = df
        return len(df)

    def save_st_snapshot(self, trade_date: date, df: pd.DataFrame) -> int:
        self.st_snapshot[trade_date.isoformat()] = df
        return len(df)


class MySqlEtlRepository:
    """MySQL 实现（需 pymysql + MySQL 实例，连接信息从 STOCK_MYSQL_* 读）。"""

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

    def save_sector_flow(self, trade_date: date, df: pd.DataFrame) -> int:  # pragma: no cover
        if self._conn is None:
            self._connect()
        sql = (
            "INSERT INTO sector_fund_flow (trade_date, name, change_pct, main_net_inflow, "
            " main_net_ratio, super_net_inflow, large_net_inflow, medium_net_inflow, "
            " small_net_inflow, leading_stock) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE main_net_inflow=VALUES(main_net_inflow), "
            " main_net_ratio=VALUES(main_net_ratio), change_pct=VALUES(change_pct)"
        )
        n = 0
        with self._conn.cursor() as cur:
            for _, row in df.iterrows():
                cur.execute(
                    sql,
                    (
                        trade_date.isoformat(),
                        row.get("name"),
                        _nan_or_none(row.get("change_pct")),
                        _nan_or_none(row.get("main_net_inflow")),
                        _nan_or_none(row.get("main_net_ratio")),
                        _nan_or_none(row.get("super_net_inflow")),
                        _nan_or_none(row.get("large_net_inflow")),
                        _nan_or_none(row.get("medium_net_inflow")),
                        _nan_or_none(row.get("small_net_inflow")),
                        row.get("leading_stock") or "",
                    ),
                )
                n += 1
        self._conn.commit()
        return n

    def save_etf_flow(self, trade_date: date, df: pd.DataFrame) -> int:  # pragma: no cover
        if self._conn is None:
            self._connect()
        sql = (
            "INSERT INTO etf_fund_flow (trade_date, code, name, amount, main_net_inflow, "
            " main_net_ratio, change_pct) VALUES (%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE main_net_inflow=VALUES(main_net_inflow), "
            " main_net_ratio=VALUES(main_net_ratio), amount=VALUES(amount), "
            " change_pct=VALUES(change_pct)"
        )
        n = 0
        with self._conn.cursor() as cur:
            for _, row in df.iterrows():
                cur.execute(
                    sql,
                    (
                        trade_date.isoformat(),
                        row.get("code"),
                        row.get("name"),
                        _nan_or_none(row.get("amount")),
                        _nan_or_none(row.get("main_net_inflow")),
                        _nan_or_none(row.get("main_net_ratio")),
                        _nan_or_none(row.get("change_pct")),
                    ),
                )
                n += 1
        self._conn.commit()
        return n

    def save_st_snapshot(self, trade_date: date, df: pd.DataFrame) -> int:  # pragma: no cover
        if self._conn is None:
            self._connect()
        # 快照覆盖式：先清空再写入（ST 名单每天整体刷新）
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM st_snapshot WHERE trade_date=%s", (trade_date.isoformat(),))
            n = 0
            for _, row in df.iterrows():
                cur.execute(
                    "INSERT INTO st_snapshot (trade_date, code, name) VALUES (%s,%s,%s)",
                    (trade_date.isoformat(), row.get("code"), row.get("name")),
                )
                n += 1
        self._conn.commit()
        return n


def _nan_or_none(value):
    """NaN → None（MySQL 不接受 NaN）。"""
    if value is None:
        return None
    try:
        import math

        if isinstance(value, float) and math.isnan(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
