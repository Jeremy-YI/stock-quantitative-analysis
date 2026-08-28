"""A股任务注册表 + 报告渲染单测。"""

from __future__ import annotations

from datetime import date

from scheduler.executor import TaskContext
from scheduler.jobs.a_share import daily_report, decay_check
from scheduler.jobs.etl_repository import InMemoryEtlRepository
from scheduler.jobs.registry import build_a_share_registry
from scheduler.jobs.sinks import InMemoryScanSink
from scheduler.sharding import InMemoryShardTracker
from strategies.signal import Signal


def _sig(symbol: str, strategy: str, signal_type: str, score: float) -> Signal:
    return Signal(
        symbol=symbol,
        strategy=strategy,
        signal_type=signal_type,
        score=score,
        triggered_at=date(2026, 8, 27),
        metrics={"pct": 3.5},
    )


def test_daily_report_renders_per_strategy_and_excess_reference():
    sink = InMemoryScanSink()
    sink.save("b1b2b3", [_sig("600001", "b1b2b3", "b1", 70.0), _sig("600002", "b1b2b3", "b2", 85.0)])
    sink.save("etf_accumulation", [_sig("588200", "etf_accumulation", "etf_accumulation", 90.0)])

    excess = {"b1b2b3": -0.5, "macd_resonance": -12.9, "pin30": -2.1,
              "stealth_rally": 6.8, "etf_accumulation": 31.5}

    result = daily_report(
        TaskContext(), sink=sink, as_of=date(2026, 8, 27), excess_reference=excess
    )
    md = result.report_markdown
    assert "每日选股报告" in md
    assert "b1b2b3（2 条）" in md
    assert "etf_accumulation（1 条）" in md
    assert "600002" in md  # 按评分排序后 B2 在前
    assert "超额胜率历史参考" in md
    # 负超额标红
    assert "macd_resonance" in md
    assert "🔴" in md


def test_daily_report_empty_signals():
    sink = InMemoryScanSink()
    result = daily_report(
        TaskContext(), sink=sink, as_of=date(2026, 8, 27), excess_reference={}
    )
    assert "— 无信号 —" in result.report_markdown
    assert "— 暂无参考数据 —" in result.report_markdown


def test_decay_check_marks_negative_excess_red():
    excess = {"b1b2b3": -0.5, "macd_resonance": -12.9, "pin30": -2.1,
              "stealth_rally": 6.8, "etf_accumulation": 31.5}
    result = decay_check(TaskContext(), decay_provider=lambda: excess)
    md = result.report_markdown
    assert "🔴 跑输市场" in md
    assert "🟢 跑赢市场" in md
    # 3 个负超额 + 摘要里点名
    assert "3 个策略" in result.summary


def test_decay_check_all_positive_no_red():
    excess = {"b1b2b3": 0.5, "macd_resonance": 1.0, "pin30": 2.0,
              "stealth_rally": 6.8, "etf_accumulation": 31.5}
    result = decay_check(TaskContext(), decay_provider=lambda: excess)
    assert "🔴 跑输市场" not in result.report_markdown
    assert "无策略" in result.summary


class _ScannerStub:
    def list_symbols(self, filter_config=None):
        return []

    def load_candles(self, as_of, filter_config=None, symbols=None):
        return {}


def test_build_a_share_registry_registers_five_jobs():
    reg = build_a_share_registry(
        _ScannerStub(), InMemoryScanSink(), InMemoryShardTracker(),
        InMemoryEtlRepository(), None,  # akshare client 用 None（ETL 任务运行时才需要）
        decay_provider=lambda: {},
        excess_reference={},
    )
    names = reg.names()
    assert names == [
        "daily_report",
        "daily_scan",
        "post_market_etl",
        "st_snapshot",
        "weekly_decay_check",
    ]
    assert reg.get("daily_scan").cron == "30 15 * * 1-5"
    assert reg.get("daily_report").notifier.value == "webhook"
    assert reg.get("weekly_decay_check").cron == "0 17 * * 6"


def test_registry_duplicate_raises():
    reg = build_a_share_registry(
        _ScannerStub(), InMemoryScanSink(), InMemoryShardTracker(),
        InMemoryEtlRepository(), None,
        decay_provider=lambda: {}, excess_reference={},
    )
    from scheduler.models import JobSpec

    import pytest

    with pytest.raises(ValueError):
        reg.register(reg.get("daily_scan"))
