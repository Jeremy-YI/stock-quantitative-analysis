"""日线 → 周线 / 月线重采样。

聚合口径（与本地脚本 `macd_monthly_water_weekly_goldencross.py::resample_ohlc`
及 pandas ``resample`` 保持一致）：

    open   取该周期内首个交易日的开盘价（first）
    high   取最大值（max）
    low    取最小值（min）
    close  取最后一个交易日的收盘价（last）
    volume 求和（sum）
    amount 求和（sum，若存在该列）

边界约定：

    - 周线按自然周聚合，锚定周五（``W-FRI``）；月线按自然月末（``ME``）。
    - 停牌 / 长假造成的空周期不生成行（``dropna`` 掉）。
    - 不完整的最后一周 / 月：只要周期内含数据就保留，open/close 取该周期内
      实际的首 / 末交易日，而非日历端点。

纯函数：只依赖 pandas，不读文件、不发请求。
"""

from __future__ import annotations

import pandas as pd

# 重采样频率（pandas 3.x 的 period 别名：'ME' = 月末，'W-FRI' = 周五锚定周）
RULE_MONTHLY = "ME"
RULE_WEEKLY = "W-FRI"

# 各列聚合方式（open/high/low/close 是 OHLC 语义，volume/amount 是累计语义）
_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
    "amount": "sum",
}


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """把日线 DataFrame 重采样成周线 / 月线。

    Args:
        df: 日线数据，至少含 ``date`` 列与 open/high/low/close/volume 列；
            ``amount`` 列可选。``date`` 可为 ``datetime.date`` 或 datetime64。
        rule: pandas 周期别名，推荐用 ``RULE_WEEKLY``（'W-FRI'）或
            ``RULE_MONTHLY``（'ME'）。

    Returns:
        以周期末交易日为 DatetimeIndex、按时间升序的 DataFrame。
        空输入返回空 DataFrame（保留原列）。
    """
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()

    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.set_index("date").sort_index()

    agg = {col: _AGG[col] for col in _AGG if col in d.columns}
    out = d.resample(rule).agg(agg)
    # 空周期（停牌/长假）agg 出来是 NaN，整行无 OHLC 意义，直接丢弃
    return out.dropna(subset=["open", "close"])


def resample_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """日线 → 周线（自然周，锚定周五）。"""
    return resample_ohlc(df, RULE_WEEKLY)


def resample_monthly(df: pd.DataFrame) -> pd.DataFrame:
    """日线 → 月线（自然月，月末）。"""
    return resample_ohlc(df, RULE_MONTHLY)
