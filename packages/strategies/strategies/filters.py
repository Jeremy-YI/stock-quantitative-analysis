"""全市场扫描的标的过滤规则。

识别逻辑参考本地脚本：
    - `macd_monthly_water_weekly_goldencross.py` 的 ``STOCK_RE``（只保留 A股个股）
    - `stealth_rally_scanner.py` 的 ``is_mainboard`` / ``BAN_PREFIXES``
    - `ticker_types.py` 的「区分个股 vs ETF/基金/指数」思想（美股 yfinance 版，
      此处按 A股代码前缀落地）

按代码前缀 + 市场判定标的种类；再叠加可配置的过滤条件（上市天数 / 成交额 /
停牌 / ST）。ST 需股票名称，由扫描器通过可选 ``name_map`` 注入，无名称时跳过 ST 过滤。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class SymbolKind(str, Enum):
    """标的种类。"""

    STOCK = "stock"  # A股个股
    ETF = "etf"  # 场内 ETF
    INDEX = "index"  # 指数（上证/深证成分等）
    CONVERTIBLE = "convertible"  # 可转债
    FUND = "fund"  # 其他基金/LOF 等


@dataclass(frozen=True)
class FilterConfig:
    """扫描过滤条件（可配置）。"""

    min_listing_days: int = 60  # 上市不足 N 个交易日剔除
    min_amount: float = 0.0  # 最新成交额下限（元），0 = 不过滤
    suspension_days: int = 20  # 最后交易日距今超过 N 个自然日视为停牌
    exclude_stock: bool = False
    exclude_etf: bool = True
    exclude_convertible: bool = True
    exclude_index: bool = True
    exclude_fund: bool = True
    exclude_st: bool = True  # 需 name_map 提供名称才生效


def classify_symbol(market: str, code: str) -> SymbolKind:
    """按市场 + 6 位代码判定标的种类。

    覆盖 A股主流前缀；不在任何已知前缀里的保守归为 FUND（宁可少测不漏个股）。
    """
    if market == "sh":
        if code.startswith(("600", "601", "603", "605", "688", "689")):
            return SymbolKind.STOCK
        if code.startswith(("110", "111", "113", "118")):
            return SymbolKind.CONVERTIBLE
        if code.startswith("000"):
            return SymbolKind.INDEX  # sh000001 上证指数等
        if code.startswith(("510", "511", "512", "513", "515", "516", "517", "518", "520", "560", "561", "562", "563", "588")):
            return SymbolKind.ETF
        return SymbolKind.FUND
    if market == "sz":
        if code.startswith(("000", "001", "002", "003", "300", "301")):
            return SymbolKind.STOCK
        if code.startswith(("123", "127", "128")):
            return SymbolKind.CONVERTIBLE
        if code.startswith("399"):
            return SymbolKind.INDEX  # sz399001 深证成指等
        if code.startswith("159"):
            return SymbolKind.ETF
        if code.startswith(("15", "16", "18")):
            return SymbolKind.FUND  # LOF/封闭基金
        return SymbolKind.FUND
    if market == "bj":
        if code.startswith(("43", "83", "87", "88", "92")):
            return SymbolKind.STOCK
        return SymbolKind.FUND
    return SymbolKind.FUND


def should_include(
    market: str,
    code: str,
    n_bars: int,
    last_trade_date: date,
    as_of: date,
    amount: float | None,
    name: str | None,
    cfg: FilterConfig,
) -> bool:
    """综合判定一只标的是否进入扫描（True = 保留）。

    Args:
        market: 交易所（sh/sz/bj）。
        code: 6 位代码。
        n_bars: 日线根数（用于「上市不足 N 日」判断）。
        last_trade_date: 最后一根 K 线的日期。
        as_of: 扫描日。
        amount: 最新成交额（元），可为 None（表示无数据）。
        name: 股票名称（可选，用于 ST 过滤）。
        cfg: 过滤配置。
    """
    if kind_excluded(classify_symbol(market, code), cfg):
        return False

    if n_bars < cfg.min_listing_days:
        return False

    # 停牌：最后交易日距扫描日太久
    if cfg.suspension_days > 0 and (as_of - last_trade_date).days > cfg.suspension_days:
        return False

    # 成交额下限
    if cfg.min_amount > 0 and (amount is None or amount < cfg.min_amount):
        return False

    # ST 过滤（需名称）
    if cfg.exclude_st and name and "ST" in name.upper():
        return False

    return True


def kind_excluded(kind: SymbolKind, cfg: FilterConfig) -> bool:
    """判断某类标的是否被配置整体剔除（在读文件前即可短路）。"""
    if kind is SymbolKind.STOCK and cfg.exclude_stock:
        return True
    if kind is SymbolKind.ETF and cfg.exclude_etf:
        return True
    if kind is SymbolKind.CONVERTIBLE and cfg.exclude_convertible:
        return True
    if kind is SymbolKind.INDEX and cfg.exclude_index:
        return True
    if kind is SymbolKind.FUND and cfg.exclude_fund:
        return True
    return False


def filter_for_kinds(kinds: tuple[SymbolKind, ...]) -> FilterConfig:
    """构造一个「只保留给定种类」的过滤配置（策略用它声明目标宇宙）。"""
    all_kinds = (
        SymbolKind.STOCK,
        SymbolKind.ETF,
        SymbolKind.CONVERTIBLE,
        SymbolKind.INDEX,
        SymbolKind.FUND,
    )
    kept = set(kinds)
    return FilterConfig(
        exclude_stock=SymbolKind.STOCK not in kept,
        exclude_etf=SymbolKind.ETF not in kept,
        exclude_convertible=SymbolKind.CONVERTIBLE not in kept,
        exclude_index=SymbolKind.INDEX not in kept,
        exclude_fund=SymbolKind.FUND not in kept,
    )
