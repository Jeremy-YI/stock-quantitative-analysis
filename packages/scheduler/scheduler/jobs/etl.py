"""盘后 ETL 任务函数。

三个 ETL 任务（对应 A股侧遗留 TODO #1、#2）：

    - ``etl_sector_flow``  板块资金流（东方财富行业资金流排名）落 MySQL。
    - ``etl_etf_flow``     ETF 资金流（场内 ETF 主力净流入）落 MySQL，
                          这是 etf_accumulation「连续净流入天数」的资金流数据源。
    - ``etl_st_snapshot``  ST 名单快照，供 strategies.filters 的 ST 过滤使用。

每个函数都通过 ``TaskContext`` 上报进度、支持中断；数据源注入 ``AkshareClient``、
落库注入 ``EtlRepository``，单测用 Fake 替换，绝不真打外部网络。
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from scheduler.executor import TaskContext
from scheduler.jobs.akshare_client import AkshareClient
from scheduler.jobs.etl_repository import EtlRepository
from scheduler.models import JobResult


def etl_sector_flow(
    ctx: TaskContext,
    client: AkshareClient,
    repo: EtlRepository,
    trade_date: date | None = None,
) -> JobResult:
    """拉取当日行业板块资金流并落库。"""
    ctx.report_progress(0.0, "拉取板块资金流")
    df = client.fetch_sector_flow()
    ctx.report_progress(0.6, f"拉到 {len(df)} 个板块，落库中")
    day = trade_date or date.today()
    n = repo.save_sector_flow(day, df)
    ctx.report_progress(1.0, f"板块资金流落库完成：{n} 行")
    top = _sector_top(df)
    return JobResult(
        summary=f"板块资金流落库 {n} 行（{day.isoformat()}）",
        report_title=f"板块资金流盘后 ETL · {day.isoformat()}",
        report_markdown=_sector_report(day, df, n),
    )


def etl_etf_flow(
    ctx: TaskContext,
    client: AkshareClient,
    repo: EtlRepository,
    trade_date: date | None = None,
) -> JobResult:
    """拉取当日场内 ETF 主力资金流并落库。"""
    ctx.report_progress(0.0, "拉取 ETF 资金流")
    df = client.fetch_etf_flow()
    ctx.report_progress(0.6, f"拉到 {len(df)} 只 ETF，落库中")
    day = trade_date or date.today()
    n = repo.save_etf_flow(day, df)
    ctx.report_progress(1.0, f"ETF 资金流落库完成：{n} 行")
    return JobResult(
        summary=f"ETF 资金流落库 {n} 行（{day.isoformat()}）",
        report_title=f"ETF 资金流盘后 ETL · {day.isoformat()}",
        report_markdown=_etf_report(day, df, n),
    )


def etl_st_snapshot(
    ctx: TaskContext,
    client: AkshareClient,
    repo: EtlRepository,
    trade_date: date | None = None,
) -> JobResult:
    """拉取 ST 名单快照并落库（供 filters 的 ST 过滤）。"""
    ctx.report_progress(0.0, "拉取 ST 名单快照")
    df = client.fetch_st_list()
    ctx.report_progress(0.6, f"拉到 {len(df)} 只 ST，落库中")
    day = trade_date or date.today()
    n = repo.save_st_snapshot(day, df)
    ctx.report_progress(1.0, f"ST 快照落库完成：{n} 行")
    return JobResult(
        summary=f"ST 名单快照落库 {n} 只（{day.isoformat()}）",
    )


# ----------------------------------------------------------------------
# 报告渲染（中文 + emoji + f-string 对齐，参考 STYLE.md 第二节）
# ----------------------------------------------------------------------

def _fmt_money(v) -> str:
    """金额格式化：亿 / 万。"""
    if v is None or pd.isna(v):
        return "—"
    if abs(v) >= 1e8:
        return f"{v / 1e8:+.2f}亿"
    return f"{v / 1e4:+.0f}万"


def _sector_top(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    if df is None or df.empty or "main_net_inflow" not in df.columns:
        return pd.DataFrame()
    return df.nlargest(n, "main_net_inflow")


def _sector_report(day: date, df: pd.DataFrame, n: int) -> str:
    lines = [f"## 板块资金流 · {day.isoformat()}", "", f"共落库 **{n}** 个行业板块。", ""]
    top = _sector_top(df)
    if not top.empty:
        lines.append("### 📈 主力净流入 TOP10")
        lines.append("")
        lines.append("```")
        lines.append(f"  {'板块':<12s} {'涨跌%':>7s} {'主力净流入':>12s} {'净占比':>7s}")
        for _, r in top.iterrows():
            lines.append(
                f"  {str(r.get('name')):<12s} "
                f"{float(r.get('change_pct') or 0):>+6.2f}% "
                f"{_fmt_money(r.get('main_net_inflow')):>12s} "
                f"{float(r.get('main_net_ratio') or 0):>+6.2f}%"
            )
        lines.append("```")
    lines.append("")
    lines.append("> 数据源：AKShare（东方财富行业资金流）。策略层不直接读外部数据，")
    lines.append("> 本表落库后供周度/月度板块总结查询。")
    return "\n".join(lines)


def _etf_report(day: date, df: pd.DataFrame, n: int) -> str:
    lines = [f"## ETF 资金流 · {day.isoformat()}", "", f"共落库 **{n}** 只场内 ETF。", ""]
    if df is not None and not df.empty and "main_net_inflow" in df.columns:
        top = df.nlargest(10, "main_net_inflow")
        lines.append("### 🔥 主力净流入 TOP10")
        lines.append("")
        lines.append("```")
        lines.append(f"  {'名称':<16s} {'代码':<8s} {'主力净流入':>12s} {'净占比':>7s}")
        for _, r in top.iterrows():
            lines.append(
                f"  {str(r.get('name'))[:16]:<16s} {str(r.get('code')):<8s} "
                f"{_fmt_money(r.get('main_net_inflow')):>12s} "
                f"{float(r.get('main_net_ratio') or 0):>+6.2f}%"
            )
        lines.append("```")
        bot = df.nsmallest(5, "main_net_inflow")
        lines.append("")
        lines.append("### 📉 主力净流出 TOP5")
        lines.append("")
        lines.append("```")
        for _, r in bot.iterrows():
            lines.append(
                f"  {str(r.get('name'))[:16]:<16s} {str(r.get('code')):<8s} "
                f"{_fmt_money(r.get('main_net_inflow')):>12s}"
            )
        lines.append("```")
    lines.append("")
    lines.append("> 该表是 etf_accumulation「连续净流入天数」的资金流数据源（阶段 3 遗留 TODO #1）。")
    return "\n".join(lines)
