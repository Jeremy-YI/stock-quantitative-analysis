"""个股推荐的名称与 ST 过滤 + 个股详情接口。

产品红线：ST / *ST / 退市整理期的股票**不能出现在推荐里**，
所以这里既测服务层判定，也测接口默认行为（include_st 显式打开才返回）。
"""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from config.settings import Settings
from main import create_app
import pandas as pd

from services.stock_meta_service import StockMetaService
from services.strategy_rating_service import StrategyRatingService
from strategies.signal import Signal

NAMES = {
    "as_of": "2026-08-31",
    "count": 4,
    "stocks": {
        "600519": {"name": "贵州茅台", "st": False},
        "000001": {"name": "平安银行", "st": False},
        "000010": {"name": "*ST美丽", "st": True},
        "600145": {"name": "退市石化", "st": True},
    },
}


class FakeSectorService:
    """板块成分股：两只正常 + 两只风险警示。"""

    def get_constituents(self, name: str) -> list[str]:
        return ["600519", "000001", "000010", "600145"]


class FakeStrategyService:
    """每个被扫到的标的都给一条信号，方便断言过滤结果。

    用 pin30（评级 oos_positive，可推荐）+ double_bottom（评级 regime，不可推荐），
    这样能同时验「评级门槛」和「ST 过滤」。
    """

    class Info:
        def __init__(self, name: str) -> None:
            self.name = name

    def list_strategies(self):
        return [self.Info("pin30"), self.Info("double_bottom")]

    def scan_subset(self, strategy: str, as_of: date, symbols: list[str]) -> list[Signal]:
        return [
            Signal(
                symbol=s,
                strategy=strategy,
                signal_type="pin30" if strategy == "pin30" else "double_bottom",
                score=80.0,
                triggered_at=as_of,
                metrics={"pct": 4.2},
            )
            for s in symbols
        ]


def _clean_bars(as_of: date, bars: int = 15) -> pd.DataFrame:
    """一段「形态干净」的日线：小实体、无长上影、量平稳，风控应放行。"""
    days = pd.bdate_range(end=as_of, periods=bars)
    return pd.DataFrame(
        {
            "date": [d.date() for d in days],
            "open": [10.0] * bars,
            "high": [10.2] * bars,
            "low": [9.9] * bars,
            "close": [10.1] * bars,
            "volume": [10000.0] * bars,
            "amount": [101000.0] * bars,
        }
    )


class FakeRepository:
    """按标的返回预置日线；默认干净形态，可注入「放量长上影」等形态。"""

    def __init__(self, frames: dict[str, pd.DataFrame] | None = None) -> None:
        self._frames = frames or {}

    def get_daily_bars(self, symbol, start=None, end=None):
        df = self._frames.get(symbol)
        if df is None:
            df = _clean_bars(end or date(2026, 8, 28))
        return df

    def set(self, symbol: str, df: pd.DataFrame) -> None:
        self._frames[symbol] = df


RATINGS = {
    "as_of": "2026-08-31",
    "strategies": {
        "pin30": {"label": "单针", "rating": "oos_positive", "client_safe": True, "reason": ""},
        "double_bottom": {"label": "双底", "rating": "regime", "client_safe": False, "reason": ""},
    },
}


@pytest.fixture()
def app(tmp_path):
    path = tmp_path / "stock_names.json"
    path.write_text(json.dumps(NAMES, ensure_ascii=False), encoding="utf-8")
    ratings_path = tmp_path / "strategy_ratings.json"
    ratings_path.write_text(json.dumps(RATINGS, ensure_ascii=False), encoding="utf-8")

    repo = FakeRepository()
    application = create_app(Settings(hsjday_root=str(tmp_path)), repository=repo)
    application.state.sector_service = FakeSectorService()
    application.state.strategy_service = FakeStrategyService()
    application.state.stock_meta_service = StockMetaService(names_path=str(path))
    application.state.strategy_rating_service = StrategyRatingService(
        ratings_path=str(ratings_path)
    )
    application.state.fake_repo = repo
    return application


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def test_meta_service_reads_names(tmp_path):
    path = tmp_path / "stock_names.json"
    path.write_text(json.dumps(NAMES, ensure_ascii=False), encoding="utf-8")
    meta = StockMetaService(names_path=str(path))

    assert meta.name("600519") == "贵州茅台"
    assert meta.name("999999") == ""  # 查不到给空串，前端显示代码
    assert meta.is_st("000010") is True
    assert meta.is_st("600145") is True
    assert meta.is_st("600519") is False
    assert meta.available() is True
    assert meta.as_of() == "2026-08-31"
    assert meta.filter_tradable(["600519", "000010", "000001"]) == ["600519", "000001"]


def test_meta_service_missing_snapshot(tmp_path):
    """快照缺失不能抛异常：名称空、不过滤（并且 available=False 让前端提示）。"""
    meta = StockMetaService(names_path=str(tmp_path / "nope.json"))
    assert meta.name("600519") == ""
    assert meta.is_st("000010") is False
    assert meta.available() is False


@pytest.mark.parametrize(
    "name,expected",
    [
        ("*ST美丽", True),
        ("ST海王", True),
        ("st康达", True),
        ("退市石化", True),
        ("贵州茅台", False),
        ("中芯国际", False),
    ],
)
def test_is_st_name_rule(name: str, expected: bool):
    """名称判定规则单测（脚本与服务共用同一套语义）。"""
    from scripts.fetch_stock_names import is_st_name  # noqa: PLC0415 - 脚本按需导入

    assert is_st_name(name) is expected


async def test_recommendations_excludes_st_by_default(app):
    async with _client(app) as c:
        res = await c.get("/api/v1/sectors/半导体/recommendations?date=2026-08-28")
    assert res.status_code == 200
    body = res.json()["body"]

    symbols = [s["symbol"] for s in body["stocks"]]
    assert symbols == ["600519", "000001"]  # 两只风险警示被剔除
    assert body["excluded_st"] == 2
    # 回测门槛：只有 pin30 参与，double_bottom 被挡
    assert body["strategies_used"] == ["pin30"]
    assert body["strategies_blocked"] == ["double_bottom"]
    assert body["names_available"] is True
    # 名称必须带上（推荐列表只给代码客户看不懂）
    assert {s["symbol"]: s["name"] for s in body["stocks"]} == {
        "600519": "贵州茅台",
        "000001": "平安银行",
    }


async def test_recommendations_include_st_opt_in(app):
    async with _client(app) as c:
        res = await c.get(
            "/api/v1/sectors/半导体/recommendations?date=2026-08-28&include_st=true"
        )
    body = res.json()["body"]
    assert len(body["stocks"]) == 4
    assert body["excluded_st"] == 0


async def test_stock_signals_endpoint(app):
    """个股详情用：单只标的的全部战法信号 + 名称。"""
    async with _client(app) as c:
        res = await c.get("/api/v1/stocks/600519/signals?date=2026-08-28")
    assert res.status_code == 200
    body = res.json()["body"]
    assert body["stocks"][0]["name"] == "贵州茅台"
    # 详情页不做评级过滤（要看清楚），但要把评级带出去
    assert {s["strategy"] for s in body["signals"]} == {"pin30", "double_bottom"}
    assert set(body["stocks"][0]["ratings"]) == {"oos_positive", "regime"}


def test_etf_name_falls_back_to_universe(tmp_path):
    """ETF 不在 A股名称表里，要能从 etf_universe.json 兜底拿到名称。

    这是「点开 ETF 看不到内容」的一半原因：名称空 + 取数 404。
    """
    import json as _json

    names = tmp_path / "stock_names.json"
    names.write_text(_json.dumps(NAMES, ensure_ascii=False), encoding="utf-8")
    etfs = tmp_path / "etf_universe.json"
    etfs.write_text(
        _json.dumps({"512480": "半导体ETF国联安", "588200": "科创芯片ETF嘉实"}, ensure_ascii=False),
        encoding="utf-8",
    )

    meta = StockMetaService(names_path=str(names), etf_names_path=str(etfs))
    assert meta.name("512480") == "半导体ETF国联安"
    assert meta.name("600519") == "贵州茅台"  # A股仍走主表
    assert meta.name("999999") == ""
    # 基金没有 ST 概念
    assert meta.is_fund("512480") is True
    assert meta.is_fund("159915") is True
    assert meta.is_fund("600519") is False
    assert meta.is_st("512480") is False


async def test_include_unverified_opens_all_strategies(app):
    """root 内部查看：include_unverified=true 时回测不过关的策略也返回。"""
    async with _client(app) as c:
        res = await c.get(
            "/api/v1/sectors/半导体/recommendations?date=2026-08-28&include_unverified=true"
        )
    body = res.json()["body"]
    assert set(body["strategies_used"]) == {"pin30", "double_bottom"}
    assert body["strategies_blocked"] == []


def _shakeout_bars(as_of: date) -> pd.DataFrame:
    """002961 瑞达期货 2026-08-28 的真实形态：放量长上影阴线（隔日 -3.02%）。"""
    days = pd.bdate_range(end=as_of, periods=6)
    opens = [18.63, 18.48, 18.75, 19.15, 20.90]
    closes = [18.51, 18.79, 19.30, 20.05, 20.56]
    highs = [18.93, 18.88, 19.82, 20.25, 21.48]
    lows = [18.33, 18.43, 18.75, 19.03, 20.35]
    vols = [47641.0, 46556.0, 97355.0, 150672.0, 228102.0]
    # 前面补一根，保证 5 日均量窗口有数据
    return pd.DataFrame(
        {
            "date": [d.date() for d in days],
            "open": [18.36] + opens,
            "high": [18.67] + highs,
            "low": [18.12] + lows,
            "close": [18.63] + closes,
            "volume": [38727.0] + vols,
            "amount": [0.0] * 6,
        }
    )


async def test_risk_filter_excludes_volume_upper_shadow(app):
    """放量长上影阴线要被风控剔除，并如实给出原因（不静默丢弃）。"""
    app.state.fake_repo.set("600519", _shakeout_bars(date(2026, 8, 28)))

    async with _client(app) as c:
        res = await c.get("/api/v1/sectors/半导体/recommendations?date=2026-08-28")
    body = res.json()["body"]

    assert [s["symbol"] for s in body["stocks"]] == ["000001"]  # 600519 被剔除
    excluded = {e["symbol"]: e["reasons"] for e in body["excluded_risk"]}
    assert "600519" in excluded
    assert any("长上影" in r for r in excluded["600519"])
    # 被剔除的股票，其信号也要从 signals 里拿掉，避免前端自己算出不一致的数字
    assert all(sig["symbol"] != "600519" for sig in body["signals"])


async def test_skip_risk_filter_flag(app):
    """root 想看原始信号时可以关掉风控。"""
    app.state.fake_repo.set("600519", _shakeout_bars(date(2026, 8, 28)))

    async with _client(app) as c:
        res = await c.get(
            "/api/v1/sectors/半导体/recommendations?date=2026-08-28&skip_risk_filter=true"
        )
    body = res.json()["body"]
    assert {s["symbol"] for s in body["stocks"]} == {"600519", "000001"}
    assert body["excluded_risk"] == []
