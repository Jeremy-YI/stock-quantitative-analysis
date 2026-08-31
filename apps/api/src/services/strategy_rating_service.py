"""策略回测评级 + 推荐风险过滤。

两件事都只有一个目的：**不把回测不过关、或当日形态明显不该买的票推给客户**。

1. 评级（data/strategy_ratings.json，由 scripts/build_strategy_ratings.py 从
   四段样本外回测机械编译）：只有 client_safe 的策略能进客户可见的推荐。
2. 风险过滤：即使策略触发，当日形态命中下面任一条也剔除——
   这三条在 docs/样本外验证报告.md 里是**四段一致的稳健结论**（放量必差、追高必差）：
     放量长上影   上影线/全长 ≥ 0.5 且 量 ≥ 1.5×5日均量     （典型滞涨出货）
     放量阴线     收 < 开 且 量 ≥ 2×5日均量
     追高         收盘偏离 MA10 ≥ +15%

   反面案例（Jeremy 2026-08-31 提出）：002961 瑞达期货 8/28 被 double_bottom 推出来，
   当日上影占 51%、量比 3.0、阴线，隔个交易日 -3.02%。评级 + 风控两道闸都能挡住它。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

_RATINGS_PATH = Path(__file__).resolve().parents[4] / "data" / "strategy_ratings.json"

# 风险过滤阈值（集中在这里，方便回测调参）
UPPER_SHADOW_RATIO = 0.5   # 上影线占全长
SHADOW_VOLUME_RATIO = 1.5  # 放量倍数（配合上影线）
BEAR_VOLUME_RATIO = 2.0    # 放量阴线倍数
CHASE_MA10_DEVIATION = 0.15  # 偏离 MA10 上限
VOLUME_MA_WINDOW = 5


class StrategyRatingService:
    """读策略评级表（无状态，懒加载）。"""

    def __init__(self, ratings_path: str | None = None) -> None:
        self._path = Path(ratings_path) if ratings_path else _RATINGS_PATH
        self._cache: dict | None = None

    def all(self) -> dict[str, dict]:
        return self._load().get("strategies", {})

    def rating(self, strategy: str) -> str:
        return self.all().get(strategy, {}).get("rating", "unknown")

    def is_client_safe(self, strategy: str) -> bool:
        """未登记的策略按「不安全」处理（宁可不推，也不推没回测过的）。"""
        return bool(self.all().get(strategy, {}).get("client_safe", False))

    def client_safe_strategies(self) -> list[str]:
        return [name for name, info in self.all().items() if info.get("client_safe")]

    def as_of(self) -> str:
        return str(self._load().get("as_of", ""))

    def available(self) -> bool:
        return bool(self.all())

    def snapshot(self) -> dict:
        """整张评级表（root 回测页要展示判定依据）。"""
        return self._load()

    def _load(self) -> dict:
        if self._cache is None:
            try:
                self._cache = json.loads(self._path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                self._cache = {}
        return self._cache


def risk_reasons(df: pd.DataFrame, as_of: date) -> list[str]:
    """返回该标的在 as_of 当日命中的风险项（空列表 = 通过）。

    df 需含 date/open/high/low/close/volume，按日期升序。
    """
    if df is None or df.empty:
        return ["无行情数据"]

    rows = df[df["date"] <= as_of]
    if rows.empty:
        return ["无行情数据"]

    last = rows.iloc[-1]
    if last["date"] != as_of:
        # 当日无成交（停牌等）→ 不推荐
        return ["当日无成交"]

    reasons: list[str] = []
    high, low, close, open_ = (
        float(last["high"]),
        float(last["low"]),
        float(last["close"]),
        float(last["open"]),
    )
    volume = float(last["volume"])

    full = high - low
    upper = high - max(open_, close)
    shadow_ratio = (upper / full) if full > 0 else 0.0

    prev = rows.iloc[-(VOLUME_MA_WINDOW + 1) : -1]
    vol_ma = float(prev["volume"].mean()) if not prev.empty else 0.0
    vol_ratio = (volume / vol_ma) if vol_ma > 0 else 0.0

    if shadow_ratio >= UPPER_SHADOW_RATIO and vol_ratio >= SHADOW_VOLUME_RATIO:
        reasons.append(f"放量长上影（上影 {shadow_ratio:.0%}，量比 {vol_ratio:.1f}）")

    if close < open_ and vol_ratio >= BEAR_VOLUME_RATIO:
        reasons.append(f"放量阴线（量比 {vol_ratio:.1f}）")

    closes = rows["close"].astype(float)
    if len(closes) >= 10:
        ma10 = float(closes.iloc[-10:].mean())
        if ma10 > 0 and (close / ma10 - 1) >= CHASE_MA10_DEVIATION:
            reasons.append(f"追高（偏离 MA10 {(close / ma10 - 1):.0%}）")

    return reasons
