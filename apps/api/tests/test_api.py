"""API 集成测试：200 / 404 / 422（用 httpx.AsyncClient + ASGITransport 打 ASGI 应用）。"""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import pandas as pd
import pytest

from config.settings import Settings
from errors import SymbolNotFoundError
from main import create_app


def _make_bars(n: int = 35) -> pd.DataFrame:
    """生成 n 根工作日日线（价格单调微涨），供内存仓储返回。"""
    dates: list[date] = []
    day = date(2026, 1, 2)
    while len(dates) < n:
        if day.weekday() < 5:
            dates.append(day)
        day += timedelta(days=1)

    closes = [round(10 + i * 0.1, 2) for i in range(n)]
    return pd.DataFrame(
        {
            "date": dates,
            "open": [round(c - 0.05, 2) for c in closes],
            "high": [round(c + 0.2, 2) for c in closes],
            "low": [round(c - 0.2, 2) for c in closes],
            "close": closes,
            "volume": [10000 + i for i in range(n)],
            "amount": [round(c * 100000, 2) for c in closes],
        }
    )


class FakeDailyBarRepository:
    """内存版仓储：已知代码返回预置日线，其余抛领域异常。"""

    def __init__(self) -> None:
        self._bars = {"600519": _make_bars()}

    def get_daily_bars(self, symbol, start=None, end=None):
        if symbol not in self._bars:
            raise SymbolNotFoundError(f"标的 {symbol} 不存在")
        df = self._bars[symbol]
        if start is not None:
            df = df[df["date"] >= start]
        if end is not None:
            df = df[df["date"] <= end]
        return df.reset_index(drop=True)


@pytest.fixture()
async def client():
    app = create_app(Settings(hsjday_root="/tmp"), repository=FakeDailyBarRepository())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_ok(client):
    res = await client.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["message"] == "ok"
    assert body["body"]["status"] == "ok"
    assert "time" in body["body"]


async def test_macd_200(client):
    res = await client.get("/api/v1/indicators/macd", params={"symbol": "600519"})
    assert res.status_code == 200
    body = res.json()
    assert body["message"] == "ok"
    assert body["body"]["symbol"] == "600519"

    series = body["body"]["series"]
    assert len(series) == 35
    assert set(series[0].keys()) == {"date", "close", "dif", "dea", "macd"}
    # 首根：EMA 首值种子 → DIF/DEA/MACD 均为 0
    assert series[0]["dif"] == 0.0
    assert series[0]["dea"] == 0.0
    assert series[0]["macd"] == 0.0


async def test_macd_404_symbol_not_found(client):
    res = await client.get("/api/v1/indicators/macd", params={"symbol": "999999"})
    assert res.status_code == 404
    assert "message" in res.json()


async def test_macd_422_invalid_symbol(client):
    # symbol 不满足 6 位数字 → FastAPI 参数校验失败，返回 422
    res = await client.get("/api/v1/indicators/macd", params={"symbol": "abc"})
    assert res.status_code == 422


async def test_macd_date_filter(client):
    res = await client.get(
        "/api/v1/indicators/macd",
        params={"symbol": "600519", "start": "2026-02-01"},
    )
    assert res.status_code == 200
    assert len(res.json()["body"]["series"]) < 35


# ---------------------------------------------------------------
# KDJ
# ---------------------------------------------------------------
async def test_kdj_200(client):
    res = await client.get("/api/v1/indicators/kdj", params={"symbol": "600519"})
    assert res.status_code == 200
    body = res.json()
    assert body["message"] == "ok"
    assert body["body"]["symbol"] == "600519"

    series = body["body"]["series"]
    assert len(series) == 35
    assert set(series[0].keys()) == {"date", "close", "k", "d", "j"}
    # 首根：前 N-1 根填充中性值 50
    assert series[0]["k"] == 50.0
    assert series[0]["d"] == 50.0
    assert series[0]["j"] == 50.0


async def test_kdj_404_symbol_not_found(client):
    res = await client.get("/api/v1/indicators/kdj", params={"symbol": "999999"})
    assert res.status_code == 404
    assert "message" in res.json()


async def test_kdj_422_invalid_symbol(client):
    res = await client.get("/api/v1/indicators/kdj", params={"symbol": "abc"})
    assert res.status_code == 422


# ---------------------------------------------------------------
# RSI
# ---------------------------------------------------------------
async def test_rsi_200(client):
    res = await client.get("/api/v1/indicators/rsi", params={"symbol": "600519"})
    assert res.status_code == 200
    body = res.json()
    assert body["message"] == "ok"
    assert body["body"]["symbol"] == "600519"

    series = body["body"]["series"]
    assert len(series) == 35
    assert set(series[0].keys()) == {"date", "close", "rsi"}
    # 首根：前 period 根填充中性值 50
    assert series[0]["rsi"] == 50.0


async def test_rsi_404_symbol_not_found(client):
    res = await client.get("/api/v1/indicators/rsi", params={"symbol": "999999"})
    assert res.status_code == 404
    assert "message" in res.json()


async def test_rsi_422_invalid_symbol(client):
    res = await client.get("/api/v1/indicators/rsi", params={"symbol": "abc"})
    assert res.status_code == 422


# ---------------------------------------------------------------
# 量能
# ---------------------------------------------------------------
async def test_volume_200(client):
    res = await client.get("/api/v1/indicators/volume", params={"symbol": "600519"})
    assert res.status_code == 200
    body = res.json()
    assert body["message"] == "ok"
    assert body["body"]["symbol"] == "600519"

    series = body["body"]["series"]
    assert len(series) == 35
    assert set(series[0].keys()) == {
        "date", "close", "volume", "mavol1", "mavol2", "volume_ratio", "relation",
    }
    # 首根：量比中性 1.0，价量关系为无数据占位
    assert series[0]["volume_ratio"] == 1.0
    assert series[0]["relation"] == "—"


async def test_volume_404_symbol_not_found(client):
    res = await client.get("/api/v1/indicators/volume", params={"symbol": "999999"})
    assert res.status_code == 404
    assert "message" in res.json()


async def test_volume_422_invalid_symbol(client):
    res = await client.get("/api/v1/indicators/volume", params={"symbol": "abc"})
    assert res.status_code == 422
