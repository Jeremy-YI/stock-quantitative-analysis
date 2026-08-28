"""回测引擎编排测试：按策略/板块聚合 + 衰减曲线 + 板块映射。"""

from __future__ import annotations

from datetime import date

import pandas as pd

from backtest.config import BacktestConfig
from backtest.engine import BacktestEngine, DictCandlesProvider, classify_board
from strategies.signal import Signal
from tests.helpers import make_candle_df


def _rising_df(start: date, n: int = 40, base: float = 10.0) -> pd.DataFrame:
    closes = [base * (1.02**i) for i in range(n)]
    return make_candle_df(closes, start=start)


def _signal(symbol: str, strategy: str, d: date) -> Signal:
    return Signal(symbol=symbol, strategy=strategy, signal_type="x", score=1.0, triggered_at=d)


def test_classify_board():
    assert classify_board("600519") == "沪市主板"
    assert classify_board("688001") == "科创板"
    assert classify_board("300750") == "创业板"
    assert classify_board("000001") == "深市主板"
    assert classify_board("430017") == "北交所"
    assert classify_board("999999") == "其他"


def test_run_verification_aggregates_by_strategy_and_board():
    d = date(2026, 6, 10)
    candles = {
        "600000": _rising_df(date(2026, 6, 1)),
        "300001": _rising_df(date(2026, 6, 1), base=20.0),
    }
    signals = [
        _signal("600000", "b1b2b3", d),
        _signal("300001", "b1b2b3", d),
        _signal("600000", "pin30", d),
    ]
    engine = BacktestEngine(DictCandlesProvider(candles))
    report = engine.run_verification(signals)

    assert report.total_signals == 3
    assert set(report.hold_days) == {1, 3, 5, 10, 20}

    strategies = {r.strategy: r for r in report.by_strategy}
    assert set(strategies) == {"b1b2b3", "pin30"}
    # b1b2b3 有 2 条信号，pin30 有 1 条
    assert strategies["b1b2b3"].holds[0].n == 2
    assert strategies["pin30"].holds[0].n == 1

    boards = {r.board: r for r in report.by_board}
    assert set(boards) == {"沪市主板", "创业板"}
    # 沪市主板有 600000 的两条（b1b2b3 + pin30）
    assert boards["沪市主板"].holds[0].n == 2
    assert boards["创业板"].holds[0].n == 1


def test_run_verification_rising_returns_positive_win_rate():
    d = date(2026, 6, 10)
    candles = {"600000": _rising_df(date(2026, 6, 1))}
    signals = [_signal("600000", "b1b2b3", d)]
    engine = BacktestEngine(DictCandlesProvider(candles))
    report = engine.run_verification(signals)

    holds = report.by_strategy[0].holds
    n1 = next(h for h in holds if h.hold_days == 1)
    # 上涨序列 → 1 日收益为正 → 胜率 100%
    assert n1.win_rate == 1.0
    assert n1.avg_return > 0


def test_compute_decay_series():
    # 跨多个交易日散布信号，衰减曲线应产生多个点
    candles = {"600000": _rising_df(date(2026, 6, 1), n=60)}
    signals = [
        _signal("600000", "b1b2b3", date(2026, 7, d)) for d in range(1, 29, 2)
    ]
    engine = BacktestEngine(DictCandlesProvider(candles))
    report = engine.run_verification(signals)

    assert len(report.decay) > 0
    by_strategy = [s for s in report.decay if s.strategy == "b1b2b3"]
    assert by_strategy
    windows = {s.window for s in by_strategy}
    assert windows == {20, 60}
    for s in by_strategy:
        assert s.points, "衰减曲线应有数据点"


def test_verification_empty_signals():
    engine = BacktestEngine(DictCandlesProvider({}))
    report = engine.run_verification([])
    assert report.total_signals == 0
    assert report.by_strategy == []
    assert report.by_board == []
    assert report.decay == []


def test_custom_hold_days_and_risk_free_rate():
    cfg = BacktestConfig()
    cfg.hold_days = [2, 4]
    cfg.risk_free_rate = 0.03
    engine = BacktestEngine(DictCandlesProvider({}), cfg)
    report = engine.run_verification([])
    assert report.hold_days == [2, 4]
