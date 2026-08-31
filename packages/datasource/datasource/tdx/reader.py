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

价格比例有个坑：**个股/可转债是 ×100，场内基金（ETF/LOF）是 ×1000**。
所以 510300 的收盘价 4.679 在文件里存的是 4679，按 /100 会读成 46.79（大 10 倍）。
统一走 resolve_price_divisor(symbol) 判定，别在调用方各写一套。
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

# 交易所前缀
# 沪市：60/68 个股，50/51/52/56/58 场内基金（588 是科创板 ETF），11/13 债，90 B股
# 深市：00/30 个股，15/16/18 场内基金，12 债，20 B股（默认归深，不用列）
# 北交所：43/83/87/88/92
_SH_PREFIXES = ("60", "68", "50", "51", "52", "56", "58", "11", "13", "90")
_BJ_PREFIXES = ("43", "83", "87", "92")

# 场内基金前缀：沪市 50/51/52/56/58（含 588 科创 ETF），深市 15/16/18
# 注意 58 是科创板 ETF、68 是科创板个股，别混
_FUND_PREFIXES = ("50", "51", "52", "56", "58", "15", "16", "18")

# 价格比例
PRICE_DIVISOR_STOCK = 100.0
PRICE_DIVISOR_FUND = 1000.0


def resolve_hsjday_root() -> Path:
    """从环境变量 ``STOCK_HSJDAY_ROOT`` 读 hsjday 根目录，缺省用本地默认路径。

    脚本 / 测试统一走这里取值，避免散落硬编码路径；缺失时给默认值而非报错，
    让「没有真实数据」的环境也能先启动（后续读文件时再明确报错）。
    """
    raw = os.environ.get("STOCK_HSJDAY_ROOT")
    return Path(raw).expanduser() if raw else DEFAULT_HSJDAY_ROOT


def resolve_market(symbol: str) -> str:
    """按代码前缀判定所属交易所。

    沪市：60/68（个股）、50/51/52/56/58（场内基金，588 = 科创板 ETF）、11/13（债）、90（B股）
    北交所：43/83/87/92
    其余归深交所（00/30 个股、15/16/18 场内基金…）。

    注意：`000001` 指深市平安银行；上证指数 `sh000001` 走的是另一套索引
    命名，不参与本函数判断。

    这里以前只认 60/68，导致沪市 ETF（512480 / 588200）被判成深市，
    取数直接 404 —— ETF 详情页打不开就是这个原因。
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


def is_fund(symbol: str) -> bool:
    """是否场内基金（ETF/LOF）。"""
    return symbol.startswith(_FUND_PREFIXES)


def resolve_price_divisor(symbol: str) -> float:
    """代码 → 价格比例：场内基金 1000，其余（个股/可转债）100。"""
    return PRICE_DIVISOR_FUND if is_fund(symbol) else PRICE_DIVISOR_STOCK


def symbol_from_path(path: str | Path) -> str:
    """从 .day 文件名反解代码：sh510300.day → 510300。"""
    stem = Path(path).stem
    return stem[2:] if len(stem) > 2 and stem[:2] in {"sh", "sz", "bj"} else stem


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


def parse_records(data: bytes, price_divisor: float = PRICE_DIVISOR_STOCK) -> list[dict]:
    """解析 .day 文件的原始字节，返回记录字典列表（纯函数，便于单测）。

    价格换算成元；比例由调用方给（个股 100 / 场内基金 1000，见 resolve_price_divisor）。
    成交量保留原始「手」。
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
                "open": op / price_divisor,
                "high": hi / price_divisor,
                "low": lo / price_divisor,
                "close": cl / price_divisor,
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

    records = parse_records(
        path.read_bytes(), resolve_price_divisor(symbol_from_path(path))
    )
    if not records:
        return pd.DataFrame(columns=COLUMNS)
    return pd.DataFrame.from_records(records, columns=COLUMNS)
