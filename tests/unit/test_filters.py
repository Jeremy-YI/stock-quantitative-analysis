"""过滤规则单元测试：标的种类识别 + 综合过滤。"""

from __future__ import annotations

from datetime import date, timedelta

from strategies.filters import (
    FilterConfig,
    SymbolKind,
    classify_symbol,
    filter_for_kinds,
    should_include,
)

AS_OF = date(2026, 8, 27)


def _recent(days_ago: int = 1) -> date:
    return AS_OF - timedelta(days=days_ago)


def test_classify_stock_prefixes():
    assert classify_symbol("sh", "600519") is SymbolKind.STOCK
    assert classify_symbol("sh", "601318") is SymbolKind.STOCK
    assert classify_symbol("sh", "688981") is SymbolKind.STOCK
    assert classify_symbol("sz", "000001") is SymbolKind.STOCK
    assert classify_symbol("sz", "002415") is SymbolKind.STOCK
    assert classify_symbol("sz", "300750") is SymbolKind.STOCK
    assert classify_symbol("bj", "430017") is SymbolKind.STOCK
    assert classify_symbol("bj", "920578") is SymbolKind.STOCK


def test_classify_etf_index_convertible_fund():
    assert classify_symbol("sh", "510050") is SymbolKind.ETF
    assert classify_symbol("sh", "588000") is SymbolKind.ETF
    assert classify_symbol("sz", "159915") is SymbolKind.ETF
    assert classify_symbol("sh", "000001") is SymbolKind.INDEX  # 上证指数
    assert classify_symbol("sz", "399001") is SymbolKind.INDEX  # 深证成指
    assert classify_symbol("sh", "110000") is SymbolKind.CONVERTIBLE
    assert classify_symbol("sz", "123000") is SymbolKind.CONVERTIBLE
    assert classify_symbol("sh", "501000") is SymbolKind.FUND


def test_filter_excludes_etf_by_default():
    cfg = FilterConfig()
    assert should_include("sh", "510050", 200, _recent(), AS_OF, 1e9, None, cfg) is False


def test_filter_keeps_stock_by_default():
    cfg = FilterConfig()
    assert should_include("sh", "600519", 200, _recent(), AS_OF, 1e9, None, cfg) is True


def test_filter_min_listing_days():
    cfg = FilterConfig(min_listing_days=60)
    assert should_include("sh", "600519", 30, _recent(), AS_OF, 1e9, None, cfg) is False
    assert should_include("sh", "600519", 100, _recent(), AS_OF, 1e9, None, cfg) is True


def test_filter_suspension():
    cfg = FilterConfig()
    # 最后交易日距今 30 自然日 > suspension_days=20 → 停牌剔除
    assert should_include("sh", "600519", 200, _recent(30), AS_OF, 1e9, None, cfg) is False
    assert should_include("sh", "600519", 200, _recent(5), AS_OF, 1e9, None, cfg) is True


def test_filter_min_amount():
    cfg = FilterConfig(min_amount=50_000_000.0)
    assert should_include("sh", "600519", 200, _recent(), AS_OF, 1e7, None, cfg) is False
    assert should_include("sh", "600519", 200, _recent(), AS_OF, 1e9, None, cfg) is True


def test_filter_st_by_name():
    cfg = FilterConfig(exclude_st=True)
    assert should_include("sh", "600519", 200, _recent(), AS_OF, 1e9, "ST某某", cfg) is False
    assert should_include("sh", "600519", 200, _recent(), AS_OF, 1e9, "贵州茅台", cfg) is True


def test_filter_for_kinds_keeps_only_target():
    cfg = filter_for_kinds((SymbolKind.ETF,))
    assert cfg.exclude_etf is False
    assert cfg.exclude_stock is True
    assert cfg.exclude_index is True
    assert cfg.exclude_fund is True
    assert cfg.exclude_convertible is True
