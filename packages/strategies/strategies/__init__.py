"""stock-strategies：A股选股策略层。

统一接口：每个策略暴露 ``scan(candles, as_of, config) -> list[Signal]``，
Signal 见 ``strategies.signal``。注册表 ``REGISTRY`` 供 API / 扫描器按名取用。
"""

from __future__ import annotations

from strategies import (
    b1b2b3,
    double_bottom,
    etf_accumulation,
    macd_resonance,
    macd_volume_washout,
    pin30,
    stealth_rally,
)
from strategies.filters import FilterConfig, SymbolKind, classify_symbol, should_include
from strategies.scanner import MarketScanner, Scanner
from strategies.signal import MetricValue, Signal

# 策略注册表：name → 策略模块（含 NAME/DESCRIPTION/scan/default_config）
REGISTRY = {
    b1b2b3.NAME: b1b2b3,
    double_bottom.NAME: double_bottom,
    macd_resonance.NAME: macd_resonance,
    pin30.NAME: pin30,
    stealth_rally.NAME: stealth_rally,
    etf_accumulation.NAME: etf_accumulation,
    macd_volume_washout.NAME: macd_volume_washout,
}

__all__ = [
    "REGISTRY",
    "FilterConfig",
    "MarketScanner",
    "MetricValue",
    "Scanner",
    "Signal",
    "SymbolKind",
    "b1b2b3",
    "classify_symbol",
    "double_bottom",
    "etf_accumulation",
    "macd_resonance",
    "macd_volume_washout",
    "pin30",
    "should_include",
    "stealth_rally",
]
