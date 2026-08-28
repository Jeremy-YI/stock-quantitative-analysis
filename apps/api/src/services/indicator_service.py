"""指标计算服务。

职责：从仓储取日线 → 调指标库算 MACD → 组装成响应结构。
不碰 HTTP，不读文件（通过仓储），保持纯业务逻辑可单测。
"""

from __future__ import annotations

from datetime import date

from indicators.macd import calc_macd
from repositories.daily_bar_repository import DailyBarRepository
from schemas.indicator import MacdBody, MacdPoint

# API 输出统一保留的小数位数（MACD 数值量级小，4 位足够且避免浮点噪声）
DECIMAL_PLACES = 4


class IndicatorService:
    """指标计算服务。"""

    def __init__(self, repository: DailyBarRepository) -> None:
        self._repository = repository

    def get_macd(
        self, symbol: str, start: date | None = None, end: date | None = None
    ) -> MacdBody:
        df = self._repository.get_daily_bars(symbol, start, end)

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
            for i, row in enumerate(df.to_dict("records"))
        ]

        return MacdBody(symbol=symbol, series=series)
