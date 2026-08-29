"""通达信 hsjday 日线数据只读解析。

数据文件位置约定：

    {hsjday_root}/{market}/lday/{market}{code}.day

其中 market ∈ {sh, sz, bj}，例如：

    sh/lday/sh600519.day
    sz/lday/sz000001.day
    bj/lday/bj430017.day

单条记录 32 字节，little-endian：

    偏移   类型    含义
    0      u32     日期（YYYYMMDD 整数，如 20260827）
    4      u32     开盘价 * 100
    8      u32     最高价 * 100
    12     u32     最低价 * 100
    16     u32     收盘价 * 100
    20     f32     成交额（元）
    24     u32     成交量（手）
    28     u32     保留位
"""

from __future__ import annotations

import os
import struct
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

import pandas as pd

RECORD_SIZE = 32

# 默认 hsjday 根目录（本地通达信导出的日线数据）。
# 通过环境变量 STOCK_HSJDAY_ROOT 可覆盖（与 config/settings.py 命名一致）。
DEFAULT_HSJDAY_ROOT = Path.home() / "Desktop" / "每日复盘" / "hsjday"
_STRUCT = struct.Struct("<IIIIIfII")

# DataFrame 列顺序（对外统一契约，字段全小写）
COLUMNS = ["date", "open", "high", "low", "close", "volume", "amount"]

# 板块前缀（阶段 1 覆盖 A 股个股，ETF/债券/北交所扩展见 TODO）
_SH_PREFIXES = ("60", "68")
_BJ_PREFIXES = ("43", "83", "87", "88", "92")


def resolve_hsjday_root() -> Path:
    """从环境变量 ``STOCK_HSJDAY_ROOT`` 读 hsjday 根目录，缺省用本地默认路径。

    脚本 / 测试统一走这里取值，避免散落硬编码路径；缺失时给默认值而非报错，
    让「没有真实数据」的环境也能先启动（后续读文件时再明确报错）。
    """
    raw = os.environ.get("STOCK_HSJDAY_ROOT")
    return Path(raw).expanduser() if raw else DEFAULT_HSJDAY_ROOT


def resolve_market(symbol: str) -> str:
    """按代码前缀判定所属交易所。

    60/68 → 上交所（sh），43/83/87/88/92 → 北交所（bj），其余归深交所（sz）。

    注意：`000001` 指深市平安银行；上证指数 `sh000001` 走的是另一套索引
    命名，不参与本函数判断。ETF/债券前缀细化列为后续 TODO。
    """
    if symbol.startswith(_SH_PREFIXES):
        return "sh"
    if symbol.startswith(_BJ_PREFIXES):
        return "bj"
    return "sz"


def resolve_symbol_path(hsjday_root: Path, symbol: str) -> Path:
    """根据 hsjday 根目录和代码，拼出该标的的 .day 文件绝对路径。"""
    market = resolve_market(symbol)
    return hsjday_root / market / "lday" / f"{market}{symbol}.day"


@lru_cache(maxsize=65536)
def _parse_date_int(date_int: int) -> date:
    """YYYYMMDD 整数 → datetime.date。

    带 lru_cache（阶段 10 内存优化）：全市场扫描要解析 6000 只 × 上千根 K 线，
    交易日总数只有几千个，缓存后
      - strptime 只跑几千次（原来上千万次），加载明显变快；
      - 所有标的**共享同一批 date 对象**，object 列只存指针，
        全市场加载峰值少掉几百 MB 的重复 date 对象。
    date 是不可变对象，共享实例不会有副作用。
    """
    return datetime.strptime(str(date_int), "%Y%m%d").date()


def parse_records(data: bytes) -> list[dict]:
    """解析 .day 文件的原始字节，返回记录字典列表（纯函数，便于单测）。

    价格统一换算成元（除以 100），成交量保留原始「手」。
    """
    records: list[dict] = []
    for offset in range(0, len(data) - RECORD_SIZE + 1, RECORD_SIZE):
        chunk = data[offset : offset + RECORD_SIZE]
        if len(chunk) < RECORD_SIZE:
            break
        date_int, op, hi, lo, cl, amount, volume, _reserved = _STRUCT.unpack(chunk)
        records.append(
            {
                "date": _parse_date_int(date_int),
                "open": op / 100.0,
                "high": hi / 100.0,
                "low": lo / 100.0,
                "close": cl / 100.0,
                "volume": volume,
                "amount": amount,
            }
        )
    return records


def parse_day_file(path: str | Path) -> pd.DataFrame:
    """读取单个 .day 文件并返回 DataFrame。

    Args:
        path: .day 文件路径。

    Returns:
        列顺序为 COLUMNS 的 DataFrame，按日期升序。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f".day 文件不存在：{path}")

    records = parse_records(path.read_bytes())
    if not records:
        return pd.DataFrame(columns=COLUMNS)
    return pd.DataFrame.from_records(records, columns=COLUMNS)
