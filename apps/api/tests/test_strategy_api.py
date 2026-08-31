"""策略 API 集成测试：200 / 404 / 422（httpx.AsyncClient + ASGITransport）。"""

from __future__ import annotations

from datetime import date

import httpx
import pandas as pd
import pytest

from config.settings import Settings
from main import create_app
from repositories.scan_result_repository import InMemoryScanResultRepository
from tests.helpers import make_candle_df


def _decline_candles() -> dict[str, pd.DataFrame]:
    """一只持续下跌的标的（触发 B1 超卖），供 fake 扫描器返回。"""
    closes = [100 * (0.98 ** i) for i in range(40)]
    return {"600001": make_candle_df(closes, high_pad=0.01, low_pad=0.01)}


class FakeScanner:
    """内存版扫描器：返回预置 candles，忽略过滤配置。"""

    def __init__(self, candles: dict[str, pd.DataFrame]) -> None:
        self._candles = candles

    def load_candles(self, as_of, filter_config=None):
        return self._candles


@pytest.fixture()
async def client():
    app = create_app(
        Settings(hsjday_root="/tmp"),
        repository=None,
        strategy_scanner=FakeScanner(_decline_candles()),
        scan_repository=InMemoryScanResultRepository(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_strategies_list_200(client):
    res = await client.get("/api/v1/strategies")
    assert res.status_code == 200
    body = res.json()
    assert body["message"] == "ok"
    names = [s["name"] for s in body["body"]["strategies"]]
    assert {"b1b2b3", "double_bottom", "macd_resonance", "pin30", "stealth_rally", "etf_accumulation"} <= set(names)
    # 每个策略都有描述与配置
    for s in body["body"]["strategies"]:
        assert s["description"]
        assert isinstance(s["config"], dict)


async def test_scan_200(client):
    res = await client.get(
        "/api/v1/strategies/b1b2b3/scan", params={"date": "2026-08-27"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["message"] == "ok"
    assert body["body"]["strategy"] == "b1b2b3"
    assert body["body"]["date"] == "2026-08-27"
    assert len(body["body"]["signals"]) > 0
    sig = body["body"]["signals"][0]
    assert sig["symbol"] == "600001"
    assert sig["strategy"] == "b1b2b3"
    assert sig["signal_type"] in {"b1", "b2", "b3"}
    assert isinstance(sig["score"], float)


async def test_scan_404_unknown_strategy(client):
    res = await client.get(
        "/api/v1/strategies/nope/scan", params={"date": "2026-08-27"}
    )
    assert res.status_code == 404
    assert "message" in res.json()


async def test_scan_422_invalid_date(client):
    res = await client.get(
        "/api/v1/strategies/b1b2b3/scan", params={"date": "not-a-date"}
    )
    assert res.status_code == 422


async def test_signals_200_after_scan(client):
    # 先扫一次落库，再查历史
    await client.get("/api/v1/strategies/b1b2b3/scan", params={"date": "2026-08-27"})
    res = await client.get("/api/v1/strategies/b1b2b3/signals")
    assert res.status_code == 200
    body = res.json()
    assert body["body"]["strategy"] == "b1b2b3"
    assert len(body["body"]["signals"]) > 0


async def test_signals_404_unknown_strategy(client):
    res = await client.get("/api/v1/strategies/nope/signals")
    assert res.status_code == 404
    assert "message" in res.json()


async def test_signals_date_filter(client):
    await client.get("/api/v1/strategies/b1b2b3/scan", params={"date": "2026-08-27"})
    # 查询一个不含该日期的区间 → 空
    res = await client.get(
        "/api/v1/strategies/b1b2b3/signals",
        params={"start": "2026-09-01", "end": "2026-09-30"},
    )
    assert res.status_code == 200
    assert res.json()["body"]["signals"] == []


# —— 市场资讯详情接口 ——
async def test_news_detail_ok(client):
    from main import create_app  # noqa: F401

    res = await client.get("/api/v1/news/walsh-hawkish-sept-rate-odds")
    assert res.status_code == 200
    body = res.json()["body"]
    assert body["item"]["id"] == "walsh-hawkish-sept-rate-odds"
    assert body["item"]["detail"]  # 有全文
    assert len(body["item"]["related_symbols"]) >= 1  # 有相关标的
    assert isinstance(body["related_news"], list)  # 相关消息（可能为空，但是列表）


async def test_news_detail_404(client):
    res = await client.get("/api/v1/news/does-not-exist")
    assert res.status_code == 404


async def test_event_detail_ok(client):
    res = await client.get("/api/v1/events/fomc-meeting")
    assert res.status_code == 200
    body = res.json()["body"]
    assert body["event"]["name"] == "美联储 FOMC 利率决议"
    assert body["event"]["description"]
    assert len(body["event"]["history"]) >= 1


async def test_event_detail_404(client):
    res = await client.get("/api/v1/events/does-not-exist")
    assert res.status_code == 404
