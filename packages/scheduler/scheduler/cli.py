"""调度器命令行入口。

用法（在仓库根目录，激活 .venv 后）：

    .venv/bin/python -m scheduler.cli list                     # 列出任务
    .venv/bin/python -m scheduler.cli run daily_scan           # 立即跑一次（手动触发）
    .venv/bin/python -m scheduler.cli trigger daily_report     # 同 run，别名
    .venv/bin/python -m scheduler.cli loop                     # 常驻循环（进程内 cron）

连接 / 路径全部从环境变量读（STOCK_MYSQL_* / STOCK_HSJDAY_ROOT /
STOCK_SCHEDULER_REPORT_DIR / STOCK_FEISHU_WEBHOOK_URL），不硬编码。
这是从旧 cron 切换到新平台的运行入口（见 docs/调度器迁移说明.md）。
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from scheduler.cron import TZ, now


def _build_scheduler():
    """组装真实调度栈（MySQL 仓储 + 本地 hsjday + AKShare）。"""
    from scheduler.executor import JobExecutor
    from scheduler.jobs.akshare_client import AkshareLiveClient
    from scheduler.jobs.etl_repository import MySqlEtlRepository
    from scheduler.jobs.registry import (
        build_a_share_registry,
        default_notifier_factory,
    )
    from scheduler.jobs.sinks import MySqlScanSink
    from scheduler.repository import MySqlRunRepository
    from scheduler.scheduler import Scheduler
    from scheduler.sharding import MySqlShardTracker
    from strategies.scanner import MarketScanner

    hsjday = os.environ.get("STOCK_HSJDAY_ROOT", "~/Desktop/每日复盘/hsjday")
    report_dir = os.environ.get("STOCK_SCHEDULER_REPORT_DIR", "~/Desktop/stock-platform/reports")
    webhook = os.environ.get("STOCK_FEISHU_WEBHOOK_URL", "") or None

    scanner = MarketScanner(Path(hsjday).expanduser())
    run_repo = MySqlRunRepository()
    shard_tracker = MySqlShardTracker()
    sink = MySqlScanSink()
    etl_repo = MySqlEtlRepository()
    akshare_client = AkshareLiveClient()

    registry = build_a_share_registry(
        scanner, sink, shard_tracker, etl_repo, akshare_client
    )
    notifier_factory = default_notifier_factory(report_dir, webhook)
    executor = JobExecutor(run_repo, notifier_factory=notifier_factory)
    return Scheduler(registry, executor, run_repo)


def _cmd_list(sched) -> None:
    jobs = sched.list_jobs()
    print(f"{'任务':<22s} {'cron':<16s} {'下次执行':<20s} {'上次状态':<8s} {'耗时':>8s}")
    print("-" * 90)
    for j in jobs:
        dur = j.get("last_duration_seconds")
        dur_s = f"{dur:.1f}s" if dur is not None else "—"
        print(
            f"{j['name']:<22s} {j['cron']:<16s} "
            f"{(j['next_run_at'] or '—')[:19]:<20s} "
            f"{(j['last_status'] or '—'):<8s} {dur_s:>8s}"
        )


def _cmd_run(sched, name: str) -> None:
    record = sched.trigger(name, trigger="manual")
    print(f"任务 {name}: {record.status.value}，耗时 {record.duration_seconds}s")
    if record.summary:
        print(f"  {record.summary}")
    if record.error:
        print(f"  错误: {record.error}")


def _cmd_loop(sched, interval: float) -> None:
    print(f"调度器循环已启动（间隔 {interval}s，时区 {TZ}）")
    while True:
        try:
            triggered = sched.run_due(now())
            for r in triggered:
                print(f"[{now().isoformat()}] 触发 {r.job_name}: {r.status.value}")
        except Exception as exc:  # noqa: BLE001 — 循环不能因单次异常退出
            print(f"[{now().isoformat()}] 调度循环异常: {exc}")
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="股票平台任务调度器")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="列出任务")
    run_p = sub.add_parser("run", help="立即跑一次任务（手动触发）")
    run_p.add_argument("name", help="任务名")
    trig_p = sub.add_parser("trigger", help="手动触发（同 run）")
    trig_p.add_argument("name", help="任务名")
    loop_p = sub.add_parser("loop", help="常驻循环（进程内 cron）")
    loop_p.add_argument("--interval", type=float, default=60.0, help="轮询间隔（秒）")

    args = parser.parse_args()

    if args.command == "list":
        _cmd_list(_build_scheduler())
    elif args.command in ("run", "trigger"):
        _cmd_run(_build_scheduler(), args.name)
    elif args.command == "loop":
        _cmd_loop(_build_scheduler(), args.interval)


if __name__ == "__main__":
    main()
