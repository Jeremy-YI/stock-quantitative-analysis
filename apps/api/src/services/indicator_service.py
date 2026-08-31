"""指标计算服务。

职责：从仓储取日线 → 调指标库算指标 → 组装成响应结构。
不碰 HTTP，不读文件（通过仓储），保持纯业务逻辑可单测。

四个端点共用「取数」这一步，所以抽了个 `_load` 小工具；序列化差异较大，
各方法自己组装 point 列表，避免过度抽象成一个难懂的通用管道。
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from indicators.kdj import calc_kdj
from indicators.macd import calc_macd
from indicators.rsi import calc_rsi
from indicators.stage14 import attack_defense_series, lifeline_series, yin_volume_line_series
from indicators.volume import calc_volume_ma, calc_volume_ratio, classify_price_volume
from repositories.daily_bar_repository import DailyBarRepository
from schemas.indicator import (
    CandlePoint,
    CandlesBody,
    KdjBody,
    KdjPoint,
    MacdBody,
    MacdPoint,
    PricingLinePoint,
    PricingLinesBody,
    RsiBody,
    RsiPoint,
    VolumeBody,
    VolumePoint,
)

# API 输出统一保留的小数位数（指标数值量级小，4 位足够且避免浮点噪声）
DECIMAL_PLACES = 4


def _opt(v: float) -> float | None:
    """NaN 转 None（定价线序列里「尚未定义」的日子返回 None 而不是 NaN）。"""
    import math
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(v, DECIMAL_PLACES)


class IndicatorService:
    """指标计算服务。"""

    def __init__(self, repository: DailyBarRepository) -> None:
        self._repository = repository

    def _load(
        self, symbol: str, start: date | None, end: date | None
    ) -> tuple[pd.DataFrame, list[dict]]:
        """取数：返回 DataFrame 及其 records 列表（供各指标共用）。"""
        df = self._repository.get_daily_bars(symbol, start, end)
        return df, df.to_dict("records")

    # ---------------------------------------------------------------
    # K 线（个股详情页画蜡烛图用）
    # ---------------------------------------------------------------
    def get_candles(
        self,
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        name: str = "",
    ) -> CandlesBody:
        """原始日 K 线（前复权与否跟仓储一致，这里只做取数 + 舍入）。"""
        _, records = self._load(symbol, start, end)
        series = [
            CandlePoint(
                date=row["date"],
                open=round(row["open"], DECIMAL_PLACES),
                high=round(row["high"], DECIMAL_PLACES),
                low=round(row["low"], DECIMAL_PLACES),
                close=round(row["close"], DECIMAL_PLACES),
                volume=float(row["volume"]),
                amount=float(row["amount"]),
            )
            for row in records
        ]
        return CandlesBody(symbol=symbol, name=name, series=series)

    # ---------------------------------------------------------------
    # MACD
    # ---------------------------------------------------------------
    def get_macd(
        self, symbol: str, start: date | None = None, end: date | None = None
    ) -> MacdBody:
        df, records = self._load(symbol, start, end)
        closes = df["close"].tolist()
        result = calc_macd(closes)

        series = [
            MacdPoint(
                date=row["date"],
                close=round(row["close"], DECIMAL_PLACES),
                dif=round(result.dif[i], DECIMAL_PLACES),
                dea=round(result.dea[i], DECIMAL_PLACES),
                macd=round(result.macd[i], DECIMAL_PLACES),
            )
            for i, row in enumerate(records)
        ]
        return MacdBody(symbol=symbol, series=series)

    # ---------------------------------------------------------------
    # KDJ
    # ---------------------------------------------------------------
    def get_kdj(
        self, symbol: str, start: date | None = None, end: date | None = None
    ) -> KdjBody:
        df, records = self._load(symbol, start, end)
        result = calc_kdj(
            df["high"].tolist(), df["low"].tolist(), df["close"].tolist()
        )

        series = [
            KdjPoint(
                date=row["date"],
                close=round(row["close"], DECIMAL_PLACES),
                k=round(result.k[i], DECIMAL_PLACES),
                d=round(result.d[i], DECIMAL_PLACES),
                j=round(result.j[i], DECIMAL_PLACES),
            )
            for i, row in enumerate(records)
        ]
        return KdjBody(symbol=symbol, series=series)

    # ---------------------------------------------------------------
    # RSI
    # ---------------------------------------------------------------
    def get_rsi(
        self, symbol: str, start: date | None = None, end: date | None = None
    ) -> RsiBody:
        df, records = self._load(symbol, start, end)
        result = calc_rsi(df["close"].tolist())

        series = [
            RsiPoint(
                date=row["date"],
                close=round(row["close"], DECIMAL_PLACES),
                rsi=round(result[i], DECIMAL_PLACES),
            )
            for i, row in enumerate(records)
        ]
        return RsiBody(symbol=symbol, series=series)

    # ---------------------------------------------------------------
    # 量能
    # ---------------------------------------------------------------
    def get_volume(
        self, symbol: str, start: date | None = None, end: date | None = None
    ) -> VolumeBody:
        df, records = self._load(symbol, start, end)
        closes = df["close"].tolist()
        volumes = df["volume"].tolist()

        ma = calc_volume_ma(volumes)
        ratio = calc_volume_ratio(volumes)
        relations = classify_price_volume(closes, volumes)

        series = [
            VolumePoint(
                date=row["date"],
                close=round(row["close"], DECIMAL_PLACES),
                volume=int(row["volume"]),
                mavol1=round(ma.mavol1[i], DECIMAL_PLACES),
                mavol2=round(ma.mavol2[i], DECIMAL_PLACES),
                volume_ratio=round(ratio[i], DECIMAL_PLACES),
                relation=relations[i],
            )
            for i, row in enumerate(records)
        ]
        return VolumeBody(symbol=symbol, series=series)

    # ---------------------------------------------------------------
    # 定价线（生命线 / 阴量定价线 / 进攻K防线）
    # ---------------------------------------------------------------
    def get_pricing_lines(
        self, symbol: str, start: date | None = None, end: date | None = None
    ) -> PricingLinesBody:
        """计算三条定价线的日度序列（阶段 12~14 的背离定价线）。"""
        df, records = self._load(symbol, start, end)
        highs = df["high"].tolist()
        lows = df["low"].tolist()
        opens = df["open"].tolist()
        closes = df["close"].tolist()
        vols = df["volume"].tolist()

        lifeline = lifeline_series(highs, lows, closes)
        yin = yin_volume_line_series(highs, lows, opens, closes, vols)
        attack = attack_defense_series(opens, highs, lows, closes, symbol)

        series = [
            PricingLinePoint(
                date=row["date"],
                close=round(row["close"], DECIMAL_PLACES),
                lifeline=_opt(lifeline[i]),
                yin_volume_line=_opt(yin[i]),
                attack_defense=_opt(attack[i]),
            )
            for i, row in enumerate(records)
        ]
        return PricingLinesBody(symbol=symbol, series=series)
