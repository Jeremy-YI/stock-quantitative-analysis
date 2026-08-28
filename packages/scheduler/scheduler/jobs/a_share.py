"""A股任务函数（调度器执行目标）。

覆盖任务书「迁移 A股侧任务」的全部五项：

    - ``daily_scan``        每日收盘全市场扫描（五策略，分片 + 断点续跑）。
    - ``daily_report``      每日选股报告（各策略信号 + 超额胜率历史参考）。
    - ``decay_check``       周度策略衰减检查（阶段 4.5 超额胜率滚动统计，
                            近 20 日超额转负标红）。
    - 盘后 ETL（板块/ETF 资金流、ST 快照）在 ``scheduler.jobs.etl``。

每个函数签名统一 ``target(ctx: TaskContext, **kwargs) -> JobResult``，由执行器
调用；通过 ``ctx.report_progress`` 上报进度、``ctx.should_stop`` 支持协作中断。
"""

from __future__ import annotations

from datetime import date
from typing import Callable

from strategies import REGISTRY
from strategies.filters import SymbolKind, filter_for_kinds
from strategies.scanner import Scanner
from strategies.signal import Signal

from scheduler.executor import TaskContext
from scheduler.jobs.sinks import ScanSink
from scheduler.models import JobResult
from scheduler.sharding import ShardTracker

# 五个策略名称（与 REGISTRY 顺序一致，报告展示顺序固定）
_STRATEGY_NAMES = [
    "b1b2b3",
    "macd_resonance",
    "pin30",
    "stealth_rally",
    "etf_accumulation",
]


def _build_shards(
    stock_symbols: list[str], etf_symbols: list[str], shard_size: int
) -> list[tuple[str, list[str]]]:
    """把个股宇宙按 shard_size 分片，ETF 宇宙整体作为最后一组。

    返回 [(kind, symbols)]，kind ∈ {"stock", "etf"}。个股分片是重头（约 5510 只），
    ETF 少（约 1458 只）故不细分。
    """
    shards: list[tuple[str, list[str]]] = []
    for i in range(0, len(stock_symbols), shard_size):
        shards.append(("stock", stock_symbols[i : i + shard_size]))
    if etf_symbols:
        shards.append(("etf", etf_symbols))
    return shards


# ----------------------------------------------------------------------
# 1. 每日收盘全市场扫描（分片 + 断点续跑）
# ----------------------------------------------------------------------

def daily_scan(
    ctx: TaskContext,
    scanner: Scanner,
    sink: ScanSink,
    shard_tracker: ShardTracker,
    job_name: str,
    as_of: date | None = None,
    shard_size: int = 500,
) -> JobResult:
    """五策略全市场扫描，结果分策略落库；分片断点续跑。

    分片标识 = (job_name, as_of.isoformat(), shard_id)。上一片已完成就跳过，
    中断（超时/异常）后下次从未完成的片继续。
    """
    day = as_of or date.today()
    batch_key = day.isoformat()

    stock_symbols = scanner.list_symbols(filter_for_kinds((SymbolKind.STOCK,)))
    etf_symbols = scanner.list_symbols(filter_for_kinds((SymbolKind.ETF,)))
    shards = _build_shards(stock_symbols, etf_symbols, shard_size)
    total = len(shards)

    counts: dict[str, int] = {name: 0 for name in _STRATEGY_NAMES}
    done = 0

    for shard_id, (kind, symbols) in enumerate(shards):
        if ctx.should_stop():
            return JobResult(
                summary=f"扫描已中断：完成 {done}/{total} 片，信号 "
                f"{sum(counts.values())} 条",
            )
        if shard_tracker.is_done(job_name, batch_key, shard_id):
            done += 1
            continue

        cfg = (
            filter_for_kinds((SymbolKind.STOCK,))
            if kind == "stock"
            else filter_for_kinds((SymbolKind.ETF,))
        )
        candles = scanner.load_candles(day, filter_config=cfg, symbols=symbols)

        for name in _STRATEGY_NAMES:
            mod = REGISTRY[name]
            # 按目标宇宙过滤：个股策略只扫 stock 片，ETF 策略只扫 etf 片
            if kind == "stock" and SymbolKind.STOCK not in mod.TARGET_KINDS:
                continue
            if kind == "etf" and SymbolKind.ETF not in mod.TARGET_KINDS:
                continue
            signals = mod.scan(candles, day)
            sink.save(name, signals)
            counts[name] += len(signals)

        shard_tracker.mark_done(job_name, batch_key, shard_id)
        done += 1
        ctx.report_progress(done / total, f"扫描 {done}/{total} 片")

    return JobResult(
        summary=f"全市场扫描完成：{done}/{total} 片，信号 {sum(counts.values())} 条",
        report_title=f"每日收盘全市场扫描 · {day.isoformat()}",
        report_markdown=_scan_report(day, counts),
    )


def _scan_report(day: date, counts: dict[str, int]) -> str:
    lines = [f"## 全市场扫描 · {day.isoformat()}", "", "### 各策略信号数", "", "```"]
    lines.append(f"  {'策略':<20s} {'信号数':>8s}")
    for name in _STRATEGY_NAMES:
        lines.append(f"  {name:<20s} {counts.get(name, 0):>8d}")
    lines.append("```")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# 2. 每日选股报告
# ----------------------------------------------------------------------

def daily_report(
    ctx: TaskContext,
    sink: ScanSink,
    as_of: date | None = None,
    excess_reference: dict[str, float | None] | None = None,
) -> JobResult:
    """读当日扫描结果，生成中文 Markdown 选股报告（含超额胜率历史参考）。"""
    day = as_of or date.today()
    ctx.report_progress(0.2, "读取当日信号")

    signals_by_strategy: dict[str, list[Signal]] = {}
    for name in _STRATEGY_NAMES:
        signals_by_strategy[name] = sink.get_signals(name, start=day, end=day)

    ctx.report_progress(0.8, "渲染报告")
    markdown = _daily_report_markdown(day, signals_by_strategy, excess_reference or {})
    ctx.report_progress(1.0, "报告生成完成")

    total = sum(len(v) for v in signals_by_strategy.values())
    return JobResult(
        summary=f"每日选股报告生成：{total} 条信号",
        report_title=f"每日选股报告 · {day.isoformat()}",
        report_markdown=markdown,
    )


def _daily_report_markdown(
    day: date,
    signals_by_strategy: dict[str, list[Signal]],
    excess_reference: dict[str, float | None],
) -> str:
    lines = [f"## 每日选股报告 · {day.isoformat()}", ""]
    for name in _STRATEGY_NAMES:
        sigs = signals_by_strategy.get(name, [])
        lines.append(f"### {name}（{len(sigs)} 条）")
        if not sigs:
            lines.append("")
            lines.append("— 无信号 —")
        else:
            top = sorted(sigs, key=lambda s: s.score, reverse=True)[:5]
            lines.append("")
            lines.append("```")
            lines.append(f"  {'代码':<8s} {'信号':<12s} {'评分':>6s}  {'要点'}")
            for s in top:
                lines.append(
                    f"  {s.symbol:<8s} {s.signal_type:<12s} {s.score:>6.1f}  "
                    f"{_metric_summary(s)}"
                )
            lines.append("```")
        lines.append("")

    lines.append("### 超额胜率历史参考（近 20 日，阶段 4.5 口径）")
    lines.append("")
    if excess_reference:
        lines.append("```")
        lines.append(f"  {'策略':<20s} {'超额胜率':>10s}")
        for name in _STRATEGY_NAMES:
            v = excess_reference.get(name)
            if v is None:
                lines.append(f"  {name:<20s} {'—':>10s}")
            else:
                flag = " 🔴" if v < 0 else ""
                lines.append(f"  {name:<20s} {v:>+9.2f}pp{flag}")
        lines.append("```")
    else:
        lines.append("— 暂无参考数据 —")
    lines.append("")
    lines.append("> 超额胜率 = 策略胜率 − 同期同宇宙基线胜率（负值表示跑输市场）。")
    return "\n".join(lines)


def _metric_summary(s: Signal) -> str:
    """把 Signal.metrics 压成一条紧凑文本。"""
    return " ".join(f"{k}={v}" for k, v in list(s.metrics.items())[:4])


# ----------------------------------------------------------------------
# 3. 周度策略衰减检查（超额胜率滚动统计，近 20 日超额转负标红）
# ----------------------------------------------------------------------

# 衰减提供者：返回 {策略名: 最近窗口超额胜率（pp）}；不可得时值为 None
DecayProvider = Callable[[], dict[str, float | None]]


def decay_check(
    ctx: TaskContext,
    decay_provider: DecayProvider,
) -> JobResult:
    """跑超额胜率滚动统计，近 20 日超额转负的策略在报告里标红。"""
    ctx.report_progress(0.1, "计算近 20 日超额胜率")
    excess = decay_provider()
    ctx.report_progress(0.8, "渲染衰减报告")
    markdown = _decay_report(excess)
    ctx.report_progress(1.0, "衰减检查完成")

    negative = [n for n in _STRATEGY_NAMES if (excess.get(n) is not None and excess[n] < 0)]
    if negative:
        summary = f"衰减检查完成：{len(negative)} 个策略近 20 日超额转负（{', '.join(negative)}）"
    else:
        summary = "衰减检查完成：无策略近 20 日超额转负"
    return JobResult(
        summary=summary,
        report_title="周度策略衰减检查",
        report_markdown=markdown,
    )


def _decay_report(excess: dict[str, float | None]) -> str:
    lines = ["## 周度策略衰减检查", "", "近 20 日超额胜率（相对同期同宇宙基线）：", ""]
    lines.append("```")
    lines.append(f"  {'策略':<20s} {'超额胜率':>10s}  {'状态'}")
    for name in _STRATEGY_NAMES:
        v = excess.get(name)
        if v is None:
            lines.append(f"  {name:<20s} {'—':>10s}  ⚪ 无数据")
        elif v < 0:
            lines.append(f"  {name:<20s} {v:>+9.2f}pp  🔴 跑输市场")
        else:
            lines.append(f"  {name:<20s} {v:>+9.2f}pp  🟢 跑赢市场")
    lines.append("```")
    lines.append("")
    lines.append("> 🔴 = 近 20 日超额转负，策略可能在失效，建议人工复核信号定义。")
    return "\n".join(lines)
