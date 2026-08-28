"""回测引擎编排测试：按策略/板块聚合 + 衰减曲线 + 板块映射。"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

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


def test_adjust_mode_default_forward_and_passthrough():
    """复权口径：默认前复权；无复权因子时价格直通（不重复复权）。"""
    from backtest.forward import forward_returns
    from market.adjust import AdjustMode

    cfg = BacktestConfig()
    assert cfg.adjust_mode == AdjustMode.FORWARD

    df = _rising_df(date(2026, 6, 1), n=10)
    signal_date = df["date"].iloc[0]
    fr = forward_returns(df, signal_date, [1])
    # 原始收盘 10 → 10.2（1.02 倍），收益 = 2%，证明未叠加任何复权调整
    assert fr[1] == pytest.approx(0.02, abs=1e-9)


def test_run_verification_excess_win_rate_and_selectivity():
    """超额胜率与选择性：一只上涨 + 一只下跌的股票宇宙，基线 1 日胜率 50%。

    策略信号只打在上涨标的上 → 策略胜率 100%，超额 = +50pp；
    选择性 = 日均 1 条信号 / 宇宙 2 只 = 0.5。
    """
    base = date(2026, 6, 1)
    rising = make_candle_df([10.0 * (1.01**i) for i in range(40)], start=base)
    falling = make_candle_df([10.0 * (0.99**i) for i in range(40)], start=base)
    candles = {"600000": rising, "300001": falling}
    kind_map = {"600000": "stock", "300001": "stock"}

    # 2026-06-18 为周四（交易日），单日区间让基线/选择性可精确断言
    d = date(2026, 6, 18)
    signals = [_signal("600000", "b1b2b3", d)]
    engine = BacktestEngine(DictCandlesProvider(candles), kind_map=kind_map)
    report = engine.run_verification(signals, start=d, end=d)

    # 基线：上涨 +0.01、下跌 -0.01 → 1 日胜率 50%
    assert len(report.baselines) == 1
    baseline = report.baselines[0]
    assert baseline.universe == "stock"
    assert baseline.size == 2
    b1 = next(h for h in baseline.holds if h.hold_days == 1)
    assert b1.win_rate == pytest.approx(0.5)

    sr = report.by_strategy[0]
    assert sr.strategy == "b1b2b3"
    assert sr.universe == "stock"
    assert sr.universe_size == 2
    assert sr.selectivity == pytest.approx(0.5)

    h1 = next(h for h in sr.holds if h.hold_days == 1)
    assert h1.win_rate == pytest.approx(1.0)
    assert h1.baseline_win_rate == pytest.approx(0.5)
    assert h1.excess_win_rate == pytest.approx(0.5)
    assert h1.excess_return == pytest.approx(0.01, abs=1e-9)


def test_overlay_matrix_marks_co_triggered():
    """叠加矩阵：同标的同日被两个策略同时触发 → 产生一条 (a,b) 叠加样本。"""
    base = date(2026, 6, 1)
    rising = make_candle_df([10.0 * (1.01**i) for i in range(40)], start=base)
    falling = make_candle_df([10.0 * (0.99**i) for i in range(40)], start=base)
    candles = {"600000": rising, "300001": falling}
    kind_map = {"600000": "stock", "300001": "stock"}

    d = date(2026, 6, 18)
    signals = [
        _signal("600000", "b1b2b3", d),
        _signal("600000", "pin30", d),
        _signal("600000", "stealth_rally", d),
    ]
    engine = BacktestEngine(DictCandlesProvider(candles), kind_map=kind_map)
    report = engine.run_verification(signals, start=d, end=d)

    assert report.overlay, "应产生叠加矩阵"
    by_pair = {(c.strategy_a, c.strategy_b): c for c in report.overlay}

    # 对角 = 单策略自身，各 1 条信号
    assert by_pair[("b1b2b3", "b1b2b3")].n == 1
    # b1b2b3 × pin30 同标的同日触发 → n=1
    assert by_pair[("b1b2b3", "pin30")].n == 1
    assert by_pair[("pin30", "stealth_rally")].n == 1
    # 叠加信号打在上涨标的上（20 日 +22%），同期基线约 50%（一涨一跌）→ 超额 > 0
    co = by_pair[("b1b2b3", "pin30")]
    assert co.win_rate == pytest.approx(1.0)
    assert co.excess_win_rate is not None and co.excess_win_rate > 0
