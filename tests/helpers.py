"""测试公共工具。"""

from __future__ import annotations

import struct
from datetime import date
from pathlib import Path

import pandas as pd

# .day 记录格式（与 datasource.tdx.reader 保持一致）
_STRUCT = struct.Struct("<IIIIIfII")

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def build_day_bytes(
    records: list[dict],
) -> bytes:
    """把记录字典列表编码成 .day 文件字节，供测试构造临时数据文件。

    Args:
        records: 每个元素含 date/open/high/low/close/volume/amount 键。
            date 为 datetime.date，价格单位为元，volume 为手，amount 为元。
    """
    buf = bytearray()
    for r in records:
        buf += _STRUCT.pack(
            int(r["date"].strftime("%Y%m%d")),
            round(r["open"] * 100),
            round(r["high"] * 100),
            round(r["low"] * 100),
            round(r["close"] * 100),
            float(r["amount"]),
            int(r["volume"]),
            0,
        )
    return bytes(buf)


def make_daily_records(
    n: int = 35, start: date = date(2026, 1, 2), base_close: float = 10.0
) -> list[dict]:
    """生成 n 根连续「工作日」的日线记录（价格单调微涨，便于断言）。"""
    from datetime import timedelta

    records: list[dict] = []
    day = start
    while len(records) < n:
        if day.weekday() < 5:
            close = base_close + len(records) * 0.1
            records.append(
                {
                    "date": day,
                    "open": close - 0.05,
                    "high": close + 0.2,
                    "low": close - 0.2,
                    "close": close,
                    "volume": 10000 + len(records),
                    "amount": close * 100000,
                }
            )
        day += timedelta(days=1)
    return records


def make_candle_df(
    closes: list[float],
    start: date = date(2025, 1, 2),
    volume: float | list[float] | None = None,
    high_pad: float = 0.05,
    low_pad: float = 0.05,
) -> pd.DataFrame:
    """由收盘价序列构造日线 DataFrame（open/high/low 用简单加减近似）。

    生成工作日日期序列（跳过周末）。volume 可为标量或序列，缺省按 close*1000。
    用于策略单测构造可控形态（急跌 / 放量大阳 / 缩量窄幅等）。
    """
    from datetime import timedelta

    n = len(closes)
    dates: list[date] = []
    day = start
    while len(dates) < n:
        if day.weekday() < 5:
            dates.append(day)
        day += timedelta(days=1)

    if volume is None:
        vols = [c * 1000.0 for c in closes]
    elif isinstance(volume, (int, float)):
        vols = [float(volume)] * n
    else:
        vols = [float(v) for v in volume]

    return pd.DataFrame(
        {
            "date": dates,
            "open": [c * (1 - 0.001) for c in closes],
            "high": [c * (1 + high_pad) for c in closes],
            "low": [c * (1 - low_pad) for c in closes],
            "close": closes,
            "volume": vols,
            "amount": [c * v for c, v in zip(closes, vols)],
        }
    )


def make_double_bottom_candles() -> dict[str, pd.DataFrame]:
    """合成一段能触发双底反弹信号的 K 线（W 底 + 底背离 + 缩量二次探底）。

    形态：高位平台 100 → 第一段主跌到左底 72 → 反弹到颈线 86 → 第二段
    缓跌到右底 73.5（略高于左底，形成底背离）→ 尾盘反弹。左右底间隔 80 根、
    右底距末根 9 根，满足 swing_k / recent / min_gap~max_gap 约束。

    供快照测试与单测构造固定回归基准（与 make_strategy_snapshots.py 一致）。
    """
    n = 240
    closes: list[float] = [0.0] * n

    def _fill(i0: int, i1: int, v0: float, v1: float) -> None:
        for i in range(i0, i1 + 1):
            if i < n:
                closes[i] = v0 + (i - i0) * (v1 - v0) / max(1, i1 - i0)

    _fill(0, 40, 100.0, 100.0)  # 高位平台（近 250 日高点）
    _fill(40, 150, 100.0, 72.0)  # 第一段主跌 → 左底 72
    _fill(150, 185, 72.0, 86.0)  # 反弹 → 颈线 86
    _fill(185, 230, 86.0, 73.5)  # 第二段缓跌 → 右底 73.5（略高，底背离）
    _fill(230, n - 1, 73.5, 75.5)  # 尾盘反弹

    # 量能：右底附近缩量（左底 3 根均量高、右底 3 根均量低 → vol_shrink < 1）
    vols = [1_000_000.0] * n
    for i in range(228, 233):
        vols[i] = 400_000.0
    return {"600519": make_candle_df(closes, volume=vols, high_pad=0.005, low_pad=0.005)}


def load_market_fixture() -> dict[str, pd.DataFrame]:
    """加载全市场抽样 fixture（scripts/make_fixtures.py 生成的 market_daily.csv）。

    返回 {6 位代码: 日线 DataFrame}。symbol 保持字符串（保留前导零）。
    """
    path = FIXTURES_DIR / "market_daily.csv"
    df = pd.read_csv(path, dtype={"symbol": str})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    candles: dict[str, pd.DataFrame] = {}
    for symbol, group in df.groupby("symbol", sort=True):
        candles[symbol] = group.drop(columns="symbol").reset_index(drop=True)
    return candles


def signals_to_json(signals) -> list[dict]:
    """把 Signal 列表序列化为 JSON 友好结构（date → isoformat，供快照对比）。"""
    return [s.model_dump(mode="json") for s in signals]

