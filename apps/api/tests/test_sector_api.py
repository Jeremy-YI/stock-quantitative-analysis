"""板块 / ETF 资金流 API 测试。

重点覆盖：
  - ETF 资金流正常返回（读快照 JSON）
  - 快照缺失时返回空体而不是 500（前端只提示「暂无数据」）
  - top 参数越界被 422 拦住
  - 路由顺序：/sectors/etf-flow 不能被 /sectors/{name} 吃掉
"""

from __future__ import annotations

import json

import httpx
import pytest

from config.settings import Settings
from main import create_app
from services.sector_service import SectorService

SNAPSHOT = {
    "date": "2026-08-28",
    "total": 954,
    "has_share_flow": False,
    "top_inflow": [
        {
            "code": "510300",
            "name": "沪深300ETF华泰柏瑞",
            "price": 4.679,
            "change_pct": -0.26,
            "net": 2.4491,
            "net_ratio": 8.64,
            "turnover": 28.351,
            "turnover_rate": 1.32,
            "mcap": 1234.5,
            "share_net": None,
        }
    ],
    "top_outflow": [
        {
            "code": "588170",
            "name": "科创半导体ETF华夏",
            "price": 1.02,
            "change_pct": -3.01,
            "net": -7.9503,
            "net_ratio": -12.1,
            "turnover": 65.7,
            "turnover_rate": 9.9,
            "mcap": 210.3,
            "share_net": -1.2,
        }
    ],
}


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture()
def app_with_snapshot(tmp_path):
    path = tmp_path / "etf_flow.json"
    path.write_text(json.dumps(SNAPSHOT, ensure_ascii=False), encoding="utf-8")
    app = create_app(Settings(hsjday_root=str(tmp_path)))
    app.state.sector_service = SectorService(etf_flow_path=str(path))
    return app


@pytest.fixture()
def app_without_snapshot(tmp_path):
    app = create_app(Settings(hsjday_root=str(tmp_path)))
    app.state.sector_service = SectorService(etf_flow_path=str(tmp_path / "missing.json"))
    return app


# 非交易日降级快照：只有主题龙头 + 上一交易日行情，资金流字段为空
LEADERS_SNAPSHOT = {
    "date": "2026-08-28",
    "total": 1121,
    "has_share_flow": False,
    "flow_available": False,
    "leaders": [
        {
            "code": "510300",
            "name": "沪深300ETF华泰柏瑞",
            "price": 4.679,
            "change_pct": -0.26,
            "net": None,
            "net_ratio": None,
            "turnover": 28.351,
            "turnover_rate": 0.0,
            "mcap": 1099.2,
            "share_net": None,
            "category": "宽基",
            "theme": "沪深300",
            "peers": 25,
        },
        {
            "code": "588200",
            "name": "科创芯片ETF嘉实",
            "price": 1.02,
            "change_pct": -2.41,
            "net": None,
            "net_ratio": None,
            "turnover": 40.0,
            "turnover_rate": 0.0,
            "mcap": 496.7,
            "share_net": None,
            "category": "科技成长",
            "theme": "半导体/芯片",
            "peers": 47,
        },
    ],
    "top_inflow": [],
    "top_outflow": [],
}


@pytest.fixture()
def app_with_leaders(tmp_path):
    path = tmp_path / "etf_flow_leaders.json"
    path.write_text(json.dumps(LEADERS_SNAPSHOT, ensure_ascii=False), encoding="utf-8")
    app = create_app(Settings(hsjday_root=str(tmp_path)))
    app.state.sector_service = SectorService(etf_flow_path=str(path))
    return app


async def test_etf_flow_ok(app_with_snapshot):
    async with _client(app_with_snapshot) as c:
        res = await c.get("/api/v1/sectors/etf-flow")
    assert res.status_code == 200
    body = res.json()["body"]
    assert body["date"] == "2026-08-28"
    assert body["total"] == 954
    assert body["has_share_flow"] is False
    assert body["top_inflow"][0]["code"] == "510300"
    assert body["top_inflow"][0]["net"] == pytest.approx(2.4491)
    # 流出侧净额为负，且份额口径允许为 None
    assert body["top_outflow"][0]["net"] < 0
    assert body["top_inflow"][0]["share_net"] is None


async def test_etf_flow_top_limits_rows(app_with_snapshot):
    async with _client(app_with_snapshot) as c:
        res = await c.get("/api/v1/sectors/etf-flow?top=1")
    assert res.status_code == 200
    assert len(res.json()["body"]["top_inflow"]) == 1


async def test_etf_flow_top_out_of_range(app_with_snapshot):
    async with _client(app_with_snapshot) as c:
        res = await c.get("/api/v1/sectors/etf-flow?top=999")
    assert res.status_code == 422


async def test_etf_flow_missing_snapshot_returns_empty(app_without_snapshot):
    """快照没生成时不能 500，给空列表让前端提示「暂无数据」。"""
    async with _client(app_without_snapshot) as c:
        res = await c.get("/api/v1/sectors/etf-flow")
    assert res.status_code == 200
    body = res.json()["body"]
    assert body == {
        "date": "",
        "total": 0,
        "has_share_flow": False,
        "flow_available": True,
        "leaders": [],
        "top_inflow": [],
        "top_outflow": [],
    }


def test_service_reads_snapshot(tmp_path):
    """服务层单测：不经过 HTTP 也要能读快照。"""
    path = tmp_path / "etf_flow.json"
    path.write_text(json.dumps(SNAPSHOT, ensure_ascii=False), encoding="utf-8")
    body = SectorService(etf_flow_path=str(path)).etf_flow(top=5)
    assert body.total == 954
    assert body.top_inflow[0].name == "沪深300ETF华泰柏瑞"
    assert body.top_outflow[0].share_net == pytest.approx(-1.2)


async def test_etf_flow_leaders(app_with_leaders):
    """主题龙头：每个主题一只代表，带大类/主题/同主题只数；非交易日资金流可为空。"""
    async with _client(app_with_leaders) as c:
        res = await c.get("/api/v1/sectors/etf-flow")
    assert res.status_code == 200
    body = res.json()["body"]
    assert body["flow_available"] is False
    assert len(body["leaders"]) == 2
    first = body["leaders"][0]
    assert first["category"] == "宽基"
    assert first["theme"] == "沪深300"
    assert first["peers"] == 25
    # 非交易日：大单口径拿不到，宁可置空也不造假数
    assert first["net"] is None
