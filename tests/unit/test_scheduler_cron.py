"""调度器 cron 解析 + 下次执行时间单测。"""

from __future__ import annotations

from datetime import datetime

import pytest

from scheduler.cron import TZ, next_run, parse_cron


def test_parse_cron_valid():
    # 不抛异常即通过
    parse_cron("0 17 * * 6")
    parse_cron("30 15 * * 1-5")
    parse_cron("*/5 * * * *")


def test_parse_cron_invalid_raises():
    with pytest.raises(ValueError):
        parse_cron("")
    with pytest.raises(ValueError):
        parse_cron("not a cron")
    with pytest.raises(ValueError):
        parse_cron("0 17 * *")  # 只有 4 段


def test_next_run_returns_aware_shanghai():
    base = datetime(2026, 8, 28, 16, 0, tzinfo=TZ)  # 周五 16:00
    nxt = next_run("0 17 * * 6", after=base)  # 周六 17:00
    assert nxt.tzinfo is not None
    assert nxt == datetime(2026, 8, 29, 17, 0, tzinfo=TZ)


def test_next_run_after_is_exclusive():
    # cron 触发点等于 after 时，应返回下一次（不含当前点）
    base = datetime(2026, 8, 29, 17, 0, tzinfo=TZ)  # 恰好周六 17:00
    nxt = next_run("0 17 * * 6", after=base)
    assert nxt == datetime(2026, 9, 5, 17, 0, tzinfo=TZ)


def test_next_run_naive_base_treated_as_shanghai():
    base = datetime(2026, 8, 28, 16, 0)  # naive
    nxt = next_run("0 17 * * 6", after=base)
    assert nxt == datetime(2026, 8, 29, 17, 0, tzinfo=TZ)
