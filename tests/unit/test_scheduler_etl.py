"""盘后 ETL 单测：AKShare 归一化 + 任务函数（用 Fake client/repo，不打外部网络）。"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from scheduler.executor import TaskContext
from scheduler.jobs.akshare_client import (
    _normalize_etf_flow,
    _normalize_sector_flow,
)
from scheduler.jobs.etl import etl_etf_flow, etl_sector_flow, etl_st_snapshot
from scheduler.jobs.etl_repository import InMemoryEtlRepository


def _raw_sector_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "名称": ["半导体", "元件", "银行"],
            "今日涨跌幅": [2.5, 1.0, -0.5],
            "今日主力净流入-净额": [1.2e8, -3.4e7, 5.0e7],
            "今日主力净流入-净占比": [8.2, -1.1, 2.3],
            "今日超大单净流入-净额": [6.0e7, -2.0e7, 1.0e7],
            "今日大单净流入-净额": [6.0e7, -1.4e7, 4.0e7],
            "今日中单净流入-净额": [-4.0e7, 1.0e7, -2.0e7],
            "今日小单净流入-净额": [-8.0e7, 2.4e7, -3.0e7],
            "今日主力净流入最大股": ["中芯国际", "生益科技", "招商银行"],
        }
    )


def _raw_etf_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "代码": ["588200", "159995", "512480"],
            "名称": ["科创半导体ETF", "芯片ETF", "半导体ETF"],
            "成交额": [1.0e8, 2.0e8, 5.0e7],
            "主力净流入-净额": [1.5e7, -2.0e7, 3.0e7],
            "主力净流入-净占比": [15.0, -10.0, 60.0],
            "涨跌幅": [1.2, -0.8, 2.5],
        }
    )


def test_normalize_sector_flow_columns():
    out = _normalize_sector_flow(_raw_sector_df())
    assert list(out.columns) == [
        "name", "change_pct", "main_net_inflow", "main_net_ratio",
        "super_net_inflow", "large_net_inflow", "medium_net_inflow",
        "small_net_inflow", "leading_stock",
    ]
    assert out.iloc[0]["name"] == "半导体"
    assert out.iloc[0]["main_net_inflow"] == 1.2e8


def test_normalize_etf_flow_columns():
    out = _normalize_etf_flow(_raw_etf_df())
    assert list(out.columns) == [
        "code", "name", "amount", "main_net_inflow", "main_net_ratio", "change_pct",
    ]
    assert out.iloc[0]["code"] == "588200"
    assert out.iloc[1]["main_net_inflow"] == -2.0e7


class FakeAkshareClient:
    def fetch_sector_flow(self):
        return _normalize_sector_flow(_raw_sector_df())

    def fetch_etf_flow(self):
        return _normalize_etf_flow(_raw_etf_df())

    def fetch_st_list(self):
        return pd.DataFrame({"code": ["600001", "000002"], "name": ["ST测试", "*ST测试"]})


def test_etl_sector_flow_task(tmp_path):
    repo = InMemoryEtlRepository()
    day = date(2026, 8, 27)
    result = etl_sector_flow(TaskContext(), client=FakeAkshareClient(), repo=repo, trade_date=day)
    assert "3 行" in result.summary
    assert "2026-08-27" in repo.sector_flow
    assert len(repo.sector_flow["2026-08-27"]) == 3
    assert result.report_markdown is not None
    assert "主力净流入 TOP10" in result.report_markdown


def test_etl_etf_flow_task():
    repo = InMemoryEtlRepository()
    day = date(2026, 8, 27)
    result = etl_etf_flow(TaskContext(), client=FakeAkshareClient(), repo=repo, trade_date=day)
    assert "3 行" in result.summary
    assert len(repo.etf_flow["2026-08-27"]) == 3


def test_etl_st_snapshot_task():
    repo = InMemoryEtlRepository()
    day = date(2026, 8, 27)
    result = etl_st_snapshot(TaskContext(), client=FakeAkshareClient(), repo=repo, trade_date=day)
    assert "2 只" in result.summary
    assert len(repo.st_snapshot["2026-08-27"]) == 2


def test_etl_normalize_empty_input():
    empty = pd.DataFrame()
    assert _normalize_sector_flow(empty).empty
    assert _normalize_etf_flow(empty).empty
