#!/usr/bin/env python3
"""阶段 10 回归校验：位置切片快路径必须与阶段 9 的布尔掩码慢路径逐条一致。

三层校验（correctness 优先于速度）：

1. **快 vs 慢（同一进程内同一份 candles）**：对抽样的若干交易日，六策略分别用
   `DaySliceView`（快）和 `df[df["date"] <= day]`（慢）扫描，信号集合
   （strategy, symbol, date）必须逐条相等。
2. **快 vs 阶段 9 落盘产物**：与 `data/oos_signals_oos-a.pkl`（阶段 9 用慢路径
   跑出来的 OOS-A 全量信号）在这些交易日上的切片对比，必须逐条相等。
   这一层能同时验证「加载改成分批 + date 对象 lru_cache」没有改变宇宙。
3. 顺带报告两条路径的耗时（同一批天，单进程）。

阶段 9 的 pkl 是 pydantic Signal（267MB，载入峰值 ~1.5GB），所以分两步跑，
不要和全市场加载叠在同一个进程里：

    # 步骤 1：抽取阶段 9 产物在抽样日上的信号键（小文件）
    .venv/bin/python scripts/check_slice_regression.py --days 8 --dump-legacy-keys
    # 步骤 2：真正的回归校验
    .venv/bin/python scripts/check_slice_regression.py --days 8 --lookback 300 \
        --exclude macd_resonance
"""

from __future__ import annotations

import argparse
import pickle
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from market.calendar import trading_days
from strategies import REGISTRY
from strategies.slicing import build_date_index

from scripts.run_oos_strategies import (  # noqa: E402
    WINDOWS,
    load_universe,
    peak_rss_mb,
    scan_day_fast,
    scan_day_slow,
)


def _keys(signals) -> set[tuple[str, str, date]]:
    return {(s.strategy, s.symbol, s.triggered_at) for s in signals}


def main() -> None:
    ap = argparse.ArgumentParser(description="位置切片快路径回归校验")
    ap.add_argument("--window", default="A")
    ap.add_argument("--days", type=int, default=8, help="抽样交易日数（均匀取自窗口）")
    ap.add_argument("--lookback", type=int, default=300)
    ap.add_argument("--exclude", nargs="*", default=["macd_resonance"])
    ap.add_argument("--legacy", default=None, help="阶段 9 信号 pkl（默认按窗口推断）")
    ap.add_argument("--dump-legacy-keys", action="store_true",
                    help="只从阶段 9 pkl 抽取抽样日的 (strategy,symbol,date) 键并落盘后退出")
    args = ap.parse_args()

    start, end = (date.fromisoformat(x) for x in WINDOWS[args.window])
    all_days = trading_days(start, end)
    step = max(1, len(all_days) // args.days)
    probe_days = all_days[::step][: args.days]
    print("窗口 %s：抽样 %d 天 %s" % (args.window, len(probe_days), [str(d) for d in probe_days]))

    legacy_path = Path(args.legacy) if args.legacy else (
        ROOT / "data" / ("oos_signals_oos-%s.pkl" % args.window.lower())
    )
    keys_path = ROOT / "data" / ("probe_keys_oos-%s_%dd.pkl" % (args.window.lower(), args.days))

    # ---- 步骤 1：只抽键，不加载全市场（避免两个大峰值叠加）----
    if args.dump_legacy_keys:
        probe_set = set(probe_days)
        raw = pickle.load(open(legacy_path, "rb"))
        by_day: dict[date, set] = {d: set() for d in probe_days}
        for s in raw:
            if s.triggered_at in probe_set:
                by_day[s.triggered_at].add((s.strategy, s.symbol, s.triggered_at))
        del raw
        keys_path.write_bytes(pickle.dumps(by_day, protocol=5))
        print("已从 %s 抽取抽样日信号 %d 条 → %s，RSS峰值 %.0fMB"
              % (legacy_path.name, sum(len(v) for v in by_day.values()),
                 keys_path.name, peak_rss_mb()))
        return

    exclude = set(args.exclude)
    legacy_by_day: dict[date, set] | None = None
    if keys_path.exists():
        legacy_by_day = {
            d: {k for k in ks if k[0] not in exclude}
            for d, ks in pickle.loads(keys_path.read_bytes()).items()
        }
        print("阶段 9 抽样键已载入 %s（%d 条）"
              % (keys_path.name, sum(len(v) for v in legacy_by_day.values())))
    else:
        print("⚠️ 未找到 %s（先跑 --dump-legacy-keys），本次只做快慢路径对比" % keys_path.name)

    t0 = time.time()
    candles, kind_map = load_universe(end, args.lookback)
    print("加载 %d 只，%.1fs，RSS峰值 %.0fMB" % (len(candles), time.time() - t0, peak_rss_mb()))

    date_index, degraded = build_date_index(candles)
    if degraded:
        print("⚠️ 非升序标的（已剔除快路径）：%s" % degraded[:10])

    symbols_by_strategy: dict[str, set[str]] = {}
    for strategy, mod in REGISTRY.items():
        if strategy in exclude:
            continue
        allowed = set(mod.TARGET_KINDS)
        symbols_by_strategy[strategy] = {
            s for s in candles if kind_map.get(s) in allowed and s in date_index
        }
    print("策略：%s" % ", ".join(sorted(symbols_by_strategy)))

    fast_t = slow_t = 0.0
    failures: list[str] = []
    for day in probe_days:
        t = time.time()
        fast = _keys(scan_day_fast(candles, date_index, symbols_by_strategy, day))
        fast_t += time.time() - t

        t = time.time()
        slow = _keys(scan_day_slow(candles, symbols_by_strategy, day))
        slow_t += time.time() - t

        ok_inner = fast == slow
        if not ok_inner:
            failures.append("%s 快慢不一致：快多 %d 条，慢多 %d 条"
                            % (day, len(fast - slow), len(slow - fast)))

        line = "  %s 快=%d 慢=%d 快慢一致=%s" % (day, len(fast), len(slow), ok_inner)
        if legacy_by_day is not None:
            legacy = legacy_by_day.get(day, set())
            ok_legacy = fast == legacy
            line += " 阶段9=%d 与阶段9一致=%s" % (len(legacy), ok_legacy)
            if not ok_legacy:
                failures.append(
                    "%s 与阶段 9 不一致：新多 %d 条 %s，旧多 %d 条 %s"
                    % (day, len(fast - legacy), sorted(fast - legacy)[:5],
                       len(legacy - fast), sorted(legacy - fast)[:5])
                )
        print(line, flush=True)

    print("\n耗时：快路径 %.1fs，慢路径 %.1fs（%d 天，单进程）" % (fast_t, slow_t, len(probe_days)))
    print("RSS峰值 %.0fMB" % peak_rss_mb())
    if failures:
        print("\n❌ 回归失败：")
        for f in failures:
            print("  " + f)
        sys.exit(1)
    print("\n✅ 回归通过：快路径与慢路径 / 阶段 9 产物逐条一致")


if __name__ == "__main__":
    main()
