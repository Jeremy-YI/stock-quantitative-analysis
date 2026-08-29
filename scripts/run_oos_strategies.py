#!/usr/bin/env python3
"""样本外（OOS）策略超额验证：七个策略在样本内 + 三段样本外区间的 20 日超额对照。

核心问题（阶段 9 最高优先级）：阶段 8 的「七策略超额排序」全部来自 2026-03~08
单区间（样本内）。本脚本把策略在三段 OOS 区间重跑，输出每段 20 日超额胜率 /
超额收益 / 选择性 / 日均信号数 / 样本量，并排对照，判定每个策略是稳健 / 过拟合 /
环境依赖。

区间：
    IS     2026-03-01 ~ 2026-08-27   （样本内，读 data/signals_cache.pkl + washout 缓存）
    OOS-A  2023-01-01 ~ 2023-12-31
    OOS-B  2024-01-01 ~ 2024-12-31
    OOS-C  2025-01-01 ~ 2026-02-28

用法（仓库根目录）：
    # 1) 只扫描（分块落盘，可断点续跑）
    .venv/bin/python scripts/run_oos_strategies.py --windows B --jobs 4 \
        --lookback 300 --exclude macd_resonance --scan-only --resume
    # 2) 汇总（读 lite 信号缓存，算 20 日超额并合并进 out JSON）
    .venv/bin/python scripts/run_oos_strategies.py --windows B --lookback 300 \
        --exclude macd_resonance --out data/oos_strategies.json

## 阶段 10 内存修复（原因 → 修法）

阶段 9 时 OOS-B/C 的全市场扫描被 macOS jetsam 反复 kill（jobs 10→2 全失败）。
四个根因，逐个修掉：

1. **`Pool(initargs=(candles, ...))` 把整个宇宙 pickle 给每个 worker**。fork 语义下
   initargs 仍要经 pipe 序列化 → 父进程一份 pickle buffer + 每个 worker 一份完整
   反序列化副本（jobs=4 就是 4 份，几百 MB × 4）。
   → 改成 **fork 前在父进程写模块级全局**，worker 通过 COW 真共享，零拷贝。
2. **布尔掩码切片 `df[df["date"] <= day]` 是复制**，且字典推导把整个宇宙的切片
   一次性物化。6000 只 × 6 策略 × 240 天 = 上百万次 DataFrame 复制。
   → 换成 `strategies.slicing.DaySliceView`：searchsorted 定位 + `iloc[:pos]`
   位置切片（视图，不复制），并且**惰性**产出，峰值 O(1)。
3. **加载期一次性物化 6000 只 × (lookback+1000) 根再裁剪**，峰值是稳态的 4 倍以上。
   → 按 400 只分批加载 + 即时裁剪。
4. **父进程累积上百万 pydantic Signal 对象**（每条含 metrics dict，~1KB）。
   → worker 只回传 `SigLite(strategy, symbol, triggered_at)`（verification 只用这三个字段），
   并按块落盘 partial，父进程内存与信号数近似线性但常数小两个数量级。

lookback：默认 300。`macd_resonance` 是唯一需要 30 月线（>660 根）的策略，
其余六策略最多回看 250 根（double_bottom 的 drawdown_window）。OOS 段一律
`--exclude macd_resonance --lookback 300`。
"""

from __future__ import annotations

import argparse
import gc
import json
import multiprocessing
import os
import pickle
import resource
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.config import BacktestConfig
from backtest.engine import BacktestEngine, DictCandlesProvider
from datasource.tdx import resolve_hsjday_root
from market.calendar import trading_days
from strategies import REGISTRY
from strategies.filters import SymbolKind, filter_for_kinds
from strategies.scanner import MarketScanner
from strategies.slicing import DaySliceView, build_date_index, mask_slice

HSJDAY = resolve_hsjday_root()
SIGNALS_CACHE = ROOT / "data" / "signals_cache.pkl"
WASHOUT_CACHE = ROOT / "data" / "macd_volume_washout_signals.pkl"

WINDOWS: dict[str, tuple[str, str]] = {
    "IS": ("2026-03-01", "2026-08-27"),
    "A": ("2023-01-01", "2023-12-31"),
    "B": ("2024-01-01", "2024-12-31"),
    "C": ("2025-01-01", "2026-02-28"),
}
WINDOW_LABELS = {"IS": "IS", "A": "OOS-A", "B": "OOS-B", "C": "OOS-C"}


class SigLite(NamedTuple):
    """轻量信号：verification / overlay / decay 只用到这三个字段。

    字段名与 ``strategies.signal.Signal`` 一致，可直接喂给 BacktestEngine。
    相比 pydantic Signal（含 score + metrics dict，实测 ~1KB/条），
    百万级信号从 GB 量级降到百 MB 量级。
    """

    strategy: str
    symbol: str
    triggered_at: date


# ----------------------------------------------------------------------------
# 内存/进度观测
# ----------------------------------------------------------------------------


def peak_rss_mb() -> float:
    """本进程峰值 RSS（MB）。macOS 上 ru_maxrss 单位是字节。"""
    v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return v / (1024 * 1024) if sys.platform == "darwin" else v / 1024


def children_peak_rss_mb() -> float:
    """所有已回收子进程的峰值 RSS 最大值（MB）。"""
    v = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return v / (1024 * 1024) if sys.platform == "darwin" else v / 1024


def mem_pressure() -> str:
    """一行系统内存快照（free / swap），用于观察是否接近 jetsam 阈值。"""
    try:
        vm = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5).stdout
        page = 16384
        free = spec = 0
        for line in vm.splitlines():
            if line.startswith("Mach Virtual Memory"):
                page = int(line.split("page size of")[1].split()[0])
            if "Pages free" in line:
                free = int(line.split(":")[1].strip().rstrip("."))
            if "Pages speculative" in line:
                spec = int(line.split(":")[1].strip().rstrip("."))
        swap = subprocess.run(
            ["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        return "free=%.0fMB swap[%s]" % ((free + spec) * page / 1e6, swap)
    except Exception:
        return "n/a"


# ----------------------------------------------------------------------------
# 全市场加载（分批 + 即时裁剪）
# ----------------------------------------------------------------------------

_EXTRA_TAIL = 1000  # 覆盖 OOS 最早窗口（2023-01）到数据末日（2026-08）的 bar 数
_LOAD_BATCH = 400  # 每批加载多少只（控制加载期峰值）


def load_universe(
    end: date,
    lookback: int = 800,
    batch: int = _LOAD_BATCH,
    verbose: bool = False,
    kinds: tuple[SymbolKind, ...] = (SymbolKind.STOCK, SymbolKind.ETF),
) -> tuple[dict, dict[str, SymbolKind]]:
    """分批加载个股 + ETF 尾段 K 线，返回 (candles, kind_map)。

    关键修正（阶段 9）：通达信 .day 文件最新到数据末日（2026-08），而 OOS 窗口
    结束日更早。``MarketScanner._read_day_tail`` 读的是「文件尾部 lookback 根」
    （末尾=数据末日），若不处理，OOS 窗口早段会被截断成空/短历史。这里多读
    ``_EXTRA_TAIL`` 根，再切到 ``date <= end`` 后取尾部 ``lookback`` 根，
    保证每个窗口都拿到「截止 end 的完整回看」。

    内存修正（阶段 10）：改成按 ``batch`` 只分批 ``load_candles(symbols=...)``，
    每批立刻裁剪到 ``lookback`` 根再并入结果。原实现先把全市场 6000 只
    × (lookback+1000) 根全部物化再裁剪，加载期峰值是稳态的 4 倍以上。
    """
    scanner = MarketScanner(HSJDAY, lookback=lookback + _EXTRA_TAIL)
    candles: dict = {}
    kind_map: dict[str, SymbolKind] = {}
    for kind in kinds:
        cfg = filter_for_kinds((kind,))
        symbols = scanner.list_symbols(filter_config=cfg)
        for i in range(0, len(symbols), batch):
            loaded = scanner.load_candles(
                end, filter_config=cfg, symbols=symbols[i : i + batch]
            )
            for symbol, df in loaded.items():
                if df is None or df.empty:
                    continue
                df = df[df["date"] <= end]
                if len(df) > lookback:
                    df = df.tail(lookback).reset_index(drop=True)
                if df.empty:
                    continue
                candles.setdefault(symbol, df)
                kind_map[symbol] = kind
            loaded.clear()
            del loaded
        if verbose:
            print(
                "    %s 加载完成，累计 %d 只，RSS峰值 %.0fMB"
                % (kind.value if hasattr(kind, "value") else kind, len(candles), peak_rss_mb()),
                flush=True,
            )
    gc.collect()
    return candles, kind_map


# ----------------------------------------------------------------------------
# 逐日扫描（快路径 = 惰性位置切片；慢路径 = 布尔掩码，保留供回归校验）
# ----------------------------------------------------------------------------


def scan_day_slow(candles: dict, symbols_by_strategy: dict[str, set[str]], day: date) -> list:
    """慢路径（阶段 9 原实现）：布尔掩码切片 + 一次性物化整个宇宙。"""
    signals = []
    for strategy, symbols in symbols_by_strategy.items():
        mod = REGISTRY[strategy]
        sliced = {
            symbol: mask_slice(candles[symbol], day)
            for symbol in symbols
            if symbol in candles
        }
        signals.extend(mod.scan(sliced, day))
    return signals


def scan_day_fast(
    candles: dict,
    date_index: dict,
    symbols_by_strategy: dict[str, set[str]],
    day: date,
) -> list:
    """快路径：searchsorted + iloc 位置切片视图，惰性产出（峰值 O(1)）。"""
    signals = []
    for strategy, symbols in symbols_by_strategy.items():
        mod = REGISTRY[strategy]
        view = DaySliceView(candles, date_index, day, symbols=symbols)
        signals.extend(mod.scan(view, day))
    return signals


# fork 前由父进程写入；worker 通过 copy-on-write 共享，不经 pickle。
_G_CANDLES: dict = {}
_G_DATE_INDEX: dict = {}
_G_SYMBOLS: dict[str, set[str]] = {}
_G_SLOW = False


def _set_globals(candles: dict, date_index: dict, symbols_by_strategy: dict, slow: bool) -> None:
    global _G_CANDLES, _G_DATE_INDEX, _G_SYMBOLS, _G_SLOW
    _G_CANDLES = candles
    _G_DATE_INDEX = date_index
    _G_SYMBOLS = symbols_by_strategy
    _G_SLOW = slow


def _scan_one(day: date) -> list[SigLite]:
    """worker 入口：返回轻量信号（不回传 pydantic Signal，省 IPC 与内存）。"""
    if _G_SLOW:
        sigs = scan_day_slow(_G_CANDLES, _G_SYMBOLS, day)
    else:
        sigs = scan_day_fast(_G_CANDLES, _G_DATE_INDEX, _G_SYMBOLS, day)
    return [SigLite(s.strategy, s.symbol, s.triggered_at) for s in sigs]


def _chunk(seq: list, size: int) -> list[list]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def scan_window(
    window: str,
    jobs: int,
    lookback: int = 800,
    exclude: set[str] | None = None,
    chunk_days: int = 20,
    resume: bool = True,
    max_days: int | None = None,
    slow: bool = False,
    partial_dir: Path | None = None,
) -> list[SigLite]:
    """逐日扫描一个窗口，按块落盘 partial（支持 --resume 跳过已完成块）。"""
    label = WINDOW_LABELS[window]
    start, end = (date.fromisoformat(x) for x in WINDOWS[window])
    t0 = time.time()
    print("  加载全市场 K 线（尾段 %d，分批 %d）..." % (lookback, _LOAD_BATCH), flush=True)
    candles, kind_map = load_universe(end, lookback, verbose=True)
    print(
        "  已加载 %d 只，耗时 %.1fs，RSS峰值 %.0fMB %s"
        % (len(candles), time.time() - t0, peak_rss_mb(), mem_pressure()),
        flush=True,
    )

    date_index: dict = {}
    degraded: list[str] = []
    if not slow:
        date_index, degraded = build_date_index(candles)
        if degraded:
            print("  ⚠️ %d 只日期非升序，已剔除快路径：%s" % (len(degraded), degraded[:5]), flush=True)

    symbols_by_strategy: dict[str, set[str]] = {}
    for strategy, mod in REGISTRY.items():
        if exclude and strategy in exclude:
            continue
        allowed = set(mod.TARGET_KINDS)
        symbols_by_strategy[strategy] = {
            s for s in candles if kind_map.get(s) in allowed and (slow or s in date_index)
        }
    print(
        "  策略 %d 个：%s"
        % (
            len(symbols_by_strategy),
            ", ".join("%s(%d)" % (k, len(v)) for k, v in sorted(symbols_by_strategy.items())),
        ),
        flush=True,
    )

    days = trading_days(start, end)
    if max_days:
        days = days[:max_days]
    blocks = _chunk(days, chunk_days)
    pdir = partial_dir or (ROOT / "data" / ("oos_partial_%s" % label.lower()))
    pdir.mkdir(parents=True, exist_ok=True)
    print(
        "  交易日 %d 个 → %d 块（每块 %d 天），jobs=%d，切片=%s"
        % (len(days), len(blocks), chunk_days, jobs, "慢(布尔掩码)" if slow else "快(位置切片)"),
        flush=True,
    )

    # fork 前写全局：worker 靠 COW 共享，不经 initargs pickle
    _set_globals(candles, date_index, symbols_by_strategy, slow)
    del kind_map
    gc.collect()

    all_signals: list[SigLite] = []
    for bi, block in enumerate(blocks, 1):
        pfile = pdir / ("chunk_%03d_%s_%s.pkl" % (bi, block[0], block[-1]))
        if resume and pfile.exists():
            try:
                payload = pickle.loads(pfile.read_bytes())
                if payload.get("days") == block:
                    all_signals.extend(payload["signals"])
                    print(
                        "  [%d/%d] 复用 %s（%d 条），累计 %d"
                        % (bi, len(blocks), pfile.name, len(payload["signals"]), len(all_signals)),
                        flush=True,
                    )
                    continue
                print("  [%d/%d] %s 天数不匹配，重扫" % (bi, len(blocks), pfile.name), flush=True)
            except Exception as exc:  # 损坏的 partial（上次被 kill 时写坏）→ 重扫
                print("  [%d/%d] %s 读取失败(%s)，重扫" % (bi, len(blocks), pfile.name, exc), flush=True)

        tb = time.time()
        block_signals: list[SigLite] = []
        if jobs > 1 and len(block) > 1:
            ctx = multiprocessing.get_context("fork")
            # 每块新建 Pool：worker 生命周期短，分配器碎片随进程退出归还系统
            with ctx.Pool(jobs) as pool:
                for sigs in pool.imap(_scan_one, block, chunksize=1):
                    block_signals.extend(sigs)
        else:
            for d in block:
                block_signals.extend(_scan_one(d))

        pfile.write_bytes(pickle.dumps({"days": block, "signals": block_signals}, protocol=5))
        n_block = len(block_signals)
        all_signals.extend(block_signals)
        del block_signals
        gc.collect()
        print(
            "  [%d/%d] %s~%s 完成，本块 %d 条，累计 %d，块耗时 %.1fs，总 %.1fs，"
            "自身RSS峰值 %.0fMB，子进程RSS峰值 %.0fMB %s"
            % (
                bi,
                len(blocks),
                block[0],
                block[-1],
                n_block,
                len(all_signals),
                time.time() - tb,
                time.time() - t0,
                peak_rss_mb(),
                children_peak_rss_mb(),
                mem_pressure(),
            ),
            flush=True,
        )

    print(
        "  扫描完成，总信号 %d，耗时 %.1fs，自身RSS峰值 %.0fMB，子进程RSS峰值 %.0fMB"
        % (len(all_signals), time.time() - t0, peak_rss_mb(), children_peak_rss_mb()),
        flush=True,
    )
    return all_signals


# ----------------------------------------------------------------------------
# 信号缓存（lite = SigLite 列表）
# ----------------------------------------------------------------------------


def lite_cache_path(label: str) -> Path:
    return ROOT / "data" / ("oos_signals_%s_lite.pkl" % label.lower())


def legacy_cache_path(label: str) -> Path:
    return ROOT / "data" / ("oos_signals_%s.pkl" % label.lower())


def load_legacy_as_lite(label: str) -> list[SigLite]:
    """把阶段 9 的 pydantic Signal 缓存转成 SigLite（单独进程跑，峰值 ~1.5GB）。"""
    path = legacy_cache_path(label)
    raw = pickle.load(open(path, "rb"))
    out = [SigLite(s.strategy, s.symbol, s.triggered_at) for s in raw]
    del raw
    gc.collect()
    return out


def load_is_signals() -> list[SigLite]:
    """IS 窗口信号：合并六策略缓存 + washout 缓存（避免重扫 124 天）。"""
    out: list[SigLite] = []
    for p in (SIGNALS_CACHE, WASHOUT_CACHE):
        if not p.exists():
            continue
        raw = pickle.load(open(p, "rb"))
        out.extend(SigLite(s.strategy, s.symbol, s.triggered_at) for s in raw)
        del raw
        gc.collect()
    return out


# ----------------------------------------------------------------------------
# 汇总
# ----------------------------------------------------------------------------


def summarize(signals: list, candles: dict, kind_map: dict, start: date, end: date) -> dict:
    """用回测引擎算 20 日超额等关键指标，返回可 JSON 化的摘要。"""
    config = BacktestConfig()
    engine = BacktestEngine(DictCandlesProvider(candles), config, kind_map=kind_map)
    verification = engine.run_verification(signals, start=start, end=end)

    headline = config.hold_days[-1]  # 20 日
    out: dict = {"baselines": {}, "strategies": {}, "total_signals": len(signals)}
    for b in verification.baselines:
        holds = {h.hold_days: {"win_rate": h.win_rate, "avg_return": h.avg_return} for h in b.holds}
        out["baselines"][b.universe] = {"size": b.size, "holds": holds}
    for sr in verification.by_strategy:
        h = next((x for x in sr.holds if x.hold_days == headline), None)
        if h is None:
            continue
        out["strategies"][sr.strategy] = {
            "universe": sr.universe,
            "signals_per_day": sr.signals_per_day,
            "selectivity": sr.selectivity,
            "n": h.n,
            "win_rate": h.win_rate,
            "avg_return": h.avg_return,
            "baseline_win_rate": h.baseline_win_rate,
            "excess_win_rate": h.excess_win_rate,
            "excess_return": h.excess_return,
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="OOS 策略超额验证")
    parser.add_argument("--windows", nargs="+", default=["IS", "A", "B", "C"],
                        help="要跑的窗口（IS/A/B/C），默认全跑")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--lookback", type=int, default=800,
                        help="单只标的回看根数（默认 800；排除 macd_resonance 后用 300 降内存）")
    parser.add_argument("--exclude", nargs="*", default=[],
                        help="要排除的策略名（如 macd_resonance）")
    parser.add_argument("--chunk-days", type=int, default=20,
                        help="每块交易日数（每块落盘 partial，支持 --resume）")
    parser.add_argument("--resume", action="store_true", help="跳过已完成的 partial 块")
    parser.add_argument("--max-days", type=int, default=None, help="只跑前 N 个交易日（烟囱测试）")
    parser.add_argument("--partial-dir", default=None,
                        help="partial 落盘目录（默认 data/oos_partial_<label>；烟囱测试建议单独指定）")
    parser.add_argument("--slow-slice", action="store_true",
                        help="用阶段 9 的布尔掩码切片（仅供内存/耗时对照）")
    parser.add_argument("--scan-only", action="store_true", help="只扫描落盘，不做汇总")
    parser.add_argument("--lite-from-legacy", action="store_true",
                        help="把阶段 9 的 pydantic 信号缓存转成 lite 缓存后退出")
    parser.add_argument("--no-merge", action="store_true", help="不合并已存在的 out JSON")
    parser.add_argument("--out", default="data/oos_strategies.json")
    args = parser.parse_args()

    exclude = set(args.exclude)
    out_path = Path(args.out)
    results: dict = {}
    if not args.no_merge and out_path.exists():
        try:
            results = json.loads(out_path.read_text(encoding="utf-8"))
            print("合并模式：已读入 %s（现有窗口 %s）" % (out_path, list(results)), flush=True)
        except Exception as exc:
            print("⚠️ 现有 %s 读取失败(%s)，改为全新写入" % (out_path, exc), flush=True)
            results = {}

    if args.lite_from_legacy:
        for window in args.windows:
            label = WINDOW_LABELS[window]
            sigs = load_legacy_as_lite(label)
            lite_cache_path(label).write_bytes(pickle.dumps(sigs, protocol=5))
            print("  %s → %s（%d 条），RSS峰值 %.0fMB"
                  % (legacy_cache_path(label).name, lite_cache_path(label).name,
                     len(sigs), peak_rss_mb()), flush=True)
        return

    for window in args.windows:
        label = WINDOW_LABELS[window]
        start, end = (date.fromisoformat(x) for x in WINDOWS[window])
        print("\n" + "=" * 80)
        print("【%s】%s ~ %s" % (label, start, end), flush=True)

        if window == "IS":
            signals = load_is_signals()
            if exclude:
                signals = [s for s in signals if s.strategy not in exclude]
            print("  读缓存信号 %d 条" % len(signals), flush=True)
        else:
            lite = lite_cache_path(label)
            legacy = legacy_cache_path(label)
            if lite.exists():
                signals = pickle.loads(lite.read_bytes())
                print("  读 lite 缓存 %d 条（%s）" % (len(signals), lite.name), flush=True)
            elif legacy.exists():
                signals = load_legacy_as_lite(label)
                lite.write_bytes(pickle.dumps(signals, protocol=5))
                print("  读旧缓存并转 lite %d 条（%s）" % (len(signals), lite.name), flush=True)
            else:
                signals = scan_window(
                    window,
                    args.jobs,
                    lookback=args.lookback,
                    exclude=exclude,
                    chunk_days=args.chunk_days,
                    resume=args.resume,
                    max_days=args.max_days,
                    slow=args.slow_slice,
                    partial_dir=Path(args.partial_dir) if args.partial_dir else None,
                )
                if not args.max_days:
                    lite.write_bytes(pickle.dumps(signals, protocol=5))
                    print("  信号缓存写入 %s" % lite.name, flush=True)
            if exclude:
                signals = [s for s in signals if s.strategy not in exclude]

        if args.scan_only:
            print("  --scan-only：跳过汇总", flush=True)
            continue

        candles, kind_map = load_universe(end, args.lookback)
        results[label] = summarize(signals, candles, kind_map, start, end)
        del signals, candles, kind_map
        gc.collect()
        print("  汇总完成，RSS峰值 %.0fMB %s" % (peak_rss_mb(), mem_pressure()), flush=True)
        # 每个窗口跑完立刻落盘，避免后面窗口被 kill 时丢结果
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.scan_only:
        return

    order = ["IS", "OOS-A", "OOS-B", "OOS-C"]
    results = {k: results[k] for k in order if k in results} | {
        k: v for k, v in results.items() if k not in order
    }
    _print_comparison(results)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n结构化快照已写入 %s" % args.out)


def _print_comparison(results: dict) -> None:
    strat_names: list[str] = []
    for label, r in results.items():
        for s in r.get("strategies", {}):
            if s not in strat_names:
                strat_names.append(s)
    strat_names.sort()

    labels = list(results.keys())
    print("\n" + "=" * 100)
    print("策略 20 日超额对照（样本内 vs 三段样本外）")
    print("=" * 100)

    for title, field, fmt in (
        ("20 日超额胜率（pp）", "excess_win_rate", lambda v: "%+.1f" % (v * 100)),
        ("20 日超额收益（%）", "excess_return", lambda v: "%+.2f" % (v * 100)),
        ("选择性（% 宇宙）", "selectivity", lambda v: "%.3f" % (v * 100)),
        ("日均信号数", "signals_per_day", lambda v: "%.1f" % v),
        ("样本量（20 日收益有效数）", "n", lambda v: "%d" % v),
        ("胜率（%）", "win_rate", lambda v: "%.1f" % (v * 100)),
    ):
        print("\n  %s：" % title)
        hdr = "    %-20s" % "策略"
        for l in labels:
            hdr += "%10s" % l
        print(hdr)
        for s in strat_names:
            row = "    %-20s" % s
            for l in labels:
                sr = results.get(l, {}).get("strategies", {}).get(s)
                v = sr.get(field) if sr else None
                row += "%10s" % ("—" if v is None else fmt(v))
            print(row)

    print("\n  基线（20 日胜率 % / 平均收益 %）：")
    for l in labels:
        bl = results.get(l, {}).get("baselines", {})
        parts = []
        for universe, b in sorted(bl.items()):
            h = b.get("holds", {}).get("20") or b.get("holds", {}).get(20)
            if h:
                parts.append(
                    "%s n=%d 胜率 %.1f%% 收益 %+.2f%%"
                    % (universe, b.get("size", 0), h["win_rate"] * 100, h["avg_return"] * 100)
                )
        print("    %-8s %s" % (l, " | ".join(parts)))


if __name__ == "__main__":
    main()
