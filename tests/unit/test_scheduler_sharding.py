"""分片断点续跑 + 全市场扫描任务单测。"""

from __future__ import annotations

from datetime import date

from scheduler.executor import TaskContext
from scheduler.jobs.a_share import daily_scan
from scheduler.jobs.sinks import InMemoryScanSink
from scheduler.sharding import InMemoryShardTracker, MySqlShardTracker


def test_shard_tracker_in_memory():
    t = InMemoryShardTracker()
    assert t.is_done("j", "2026-08-27", 0) is False
    t.mark_done("j", "2026-08-27", 0)
    assert t.is_done("j", "2026-08-27", 0) is True
    assert t.is_done("j", "2026-08-27", 1) is False
    assert t.done_shards("j", "2026-08-27") == {0}
    # 不同批次互不影响
    assert t.done_shards("j", "2026-08-28") == set()


def test_shard_tracker_mysql_is_lazy_until_connect():
    # 构造不连接（惰性），只是确认类可实例化
    tracker = MySqlShardTracker()
    assert tracker is not None


class FakeScanner:
    """内存版扫描器：按 symbols 参数返回预置 candles，并记录每次加载的符号。"""

    def __init__(self, stock_symbols: list[str], etf_symbols: list[str]):
        self._stock = stock_symbols
        self._etf = etf_symbols
        self.loaded_batches: list[set[str]] = []

    def list_symbols(self, filter_config=None) -> list[str]:
        # filter_config.exclude_etf 决定返回个股还是 ETF
        if filter_config.exclude_etf:
            return list(self._stock)
        return list(self._etf)

    def load_candles(self, as_of, filter_config=None, symbols=None):
        import pandas as pd

        syms = list(symbols) if symbols is not None else []
        self.loaded_batches.append(set(syms))
        out = {}
        for s in syms:
            out[s] = _tiny_df()
        return out


def _tiny_df():
    import pandas as pd

    closes = [10.0 + i * 0.01 for i in range(40)]
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-02", periods=40, freq="B"),
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [10000.0] * 40,
            "amount": [c * 10000 for c in closes],
        }
    )


def _noop_ctx() -> TaskContext:
    return TaskContext()


def test_daily_scan_sharding_resume_skips_done_shards():
    """构造中断场景：第一轮完成 2 片后中断，第二轮只跑未完成的片。"""
    stock = [f"60{i:04d}" for i in range(8)]  # 8 只个股
    scanner = FakeScanner(stock, etf_symbols=[])
    sink = InMemoryScanSink()
    tracker = InMemoryShardTracker()
    day = date(2026, 8, 27)

    # 第一轮：跑到第 2 片后中断（模拟超时）
    class _StopCtx:
        def __init__(self):
            self._calls = 0

        def report_progress(self, *a, **k):
            pass

        def should_stop(self):
            self._calls += 1
            # 第 3 次询问时（第 3 片开始前）请求中断
            return self._calls >= 3

    result1 = daily_scan(
        _StopCtx(), scanner=scanner, sink=sink, shard_tracker=tracker,
        job_name="daily_scan", as_of=day, shard_size=3,
    )
    assert "中断" in result1.summary
    # 8 只 / 3 = 3 片（3+3+2），中断时已完成 2 片
    assert tracker.done_shards("daily_scan", "2026-08-27") == {0, 1}

    # 第二轮：用全新 ctx（不中断），应跳过已完成的前 2 片，只跑第 3 片
    first_round_batches = scanner.loaded_batches
    scanner.loaded_batches = []
    result2 = daily_scan(
        _noop_ctx(), scanner=scanner, sink=sink, shard_tracker=tracker,
        job_name="daily_scan", as_of=day, shard_size=3,
    )
    assert "完成" in result2.summary
    # 第二轮只加载了第 3 片的符号（剩余 2 只）
    assert len(scanner.loaded_batches) == 1
    assert scanner.loaded_batches[0] == set(stock[6:8])
    assert tracker.done_shards("daily_scan", "2026-08-27") == {0, 1, 2}


def test_daily_scan_full_run_all_shards():
    stock = [f"60{i:04d}" for i in range(5)]
    scanner = FakeScanner(stock, etf_symbols=[])
    sink = InMemoryScanSink()
    tracker = InMemoryShardTracker()
    day = date(2026, 8, 27)

    result = daily_scan(
        _noop_ctx(), scanner=scanner, sink=sink, shard_tracker=tracker,
        job_name="daily_scan", as_of=day, shard_size=2,
    )
    assert "完成" in result.summary
    assert tracker.done_shards("daily_scan", "2026-08-27") == {0, 1, 2}
    # 个股策略有信号落库（b1 超卖等在单调上涨数据上可能不触发，但扫描本身完成）
    assert result.report_markdown is not None
