"""cron 表达式解析与下次执行时间计算。

时区固定 Asia/Shanghai（A股 / 美股脚本都以上海时间对齐），用成熟库
``croniter`` 解析，不自己写解析器。所有返回的 datetime 都是 Asia/Shanghai
时区的 aware 对象。
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from croniter import croniter

TZ = ZoneInfo("Asia/Shanghai")
TZ_NAME = "Asia/Shanghai"


def now() -> datetime:
    """当前上海时间（aware）。"""
    return datetime.now(TZ)


def parse_cron(expr: str) -> None:
    """校验 cron 表达式；非法时抛出 ``ValueError``（含清晰提示）。"""
    if not expr or not expr.strip():
        raise ValueError("cron 表达式不能为空")
    try:
        croniter(expr, now())
    except Exception as exc:  # croniter 抛 ValueError / KeyError
        raise ValueError(f"非法 cron 表达式 {expr!r}: {exc}") from exc


def next_run(expr: str, after: datetime | None = None) -> datetime:
    """返回 ``after`` 之后的下一次执行时间（Asia/Shanghai aware）。

    ``after`` 缺省为当前上海时间。返回 aware datetime（时区已固定上海）。
    """
    base = after or now()
    if base.tzinfo is None:
        # 容错：调用方传了 naive datetime 时按上海时区解释
        base = base.replace(tzinfo=TZ)
    it = croniter(expr, base)
    return it.get_next(datetime)
