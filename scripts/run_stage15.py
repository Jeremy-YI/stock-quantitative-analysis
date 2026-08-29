#!/usr/bin/env python3
"""阶段 15：2020-01 ~ 2026-08「深水单针」季度滚动验证（27 个独立检验窗口）。

## 为什么做这个

阶段 12~14 只有 4 个检验窗口（IS 半年 + OOS-A/B/C 三段），深水单针在这 4 段的
25/60 日超额全正。但 4 个窗口撑不起「稳健」二字——窗口本身是人选的。本阶段把区间
拉到 2020-01-01 ~ 2026-08-28（数据末日），**按自然季度切成 27 个独立检验窗口**
（A 股按季度披露财报，季度是天然的信息边界），然后做符号检验：如果规则无效，
27 个季度的超额应该正负各半。

## 被检验的规则（唯一在前几阶段存活的那条）

**深水单针**（阶段 12 的桶3）：
    非趋势多头（ST_RAW = EMA(EMA(C,10),10) <= LT_RAW = (MA14+MA28+MA57+MA114)/4
    或 C <= LT_RAW）
    且 长期随机(20 日) <= 55
    且 短期随机(3 日) <= 30（另测 <= 20）
    → 信号日**收盘价**买入，持有 20 / 25 / 60 个交易日。

对照组：
1. **原始单针**（阶段 12 的桶1）：趋势多头 且 长期随机 >= 80 且 短期随机 <= 30。
   前几阶段测出四段负超额，这里看 27 个季度是不是也一致为负。
2. **全市场等权基线**：每季度**单独**算（同季度、同宇宙、同「>=120 根前置 K 线」
   约束的所有股票-日，持有同样天数），超额 = 规则收益 − **同季度**基线收益。

## 实现路线（为什么不是逐日全市场扫描）

深水单针是「每只股票只依赖自己历史」的纯函数规则，不需要 `DaySliceView`
的逐日全市场切片。这里改成：

    逐股读全历史 → 一次算全序列指标 → 向量化算 20/25/60 日前向收益 / MAE / MFE
    → 按「季度 × 季报窗口分组」bincount 累加 → 丢弃该股，处理下一只

内存 O(单只股票)（峰值 RSS 实测 < 300MB），速度比逐日扫描快一到两个数量级。
等价性由 `--verify-stage14` 回归校验：用阶段 14 的 `load_universe` 加载同样的
四段窗口帧，跑本脚本的向量化累加，与 `data/stage14_backtest.json` 的组1 数字对齐。

## 无前视纪律

- 买入价 = 信号日收盘价（信号在收盘后才成立，收盘买是最乐观但可执行的口径）。
- 指标全部只用 t 及更早的 bar（rolling / EMA / SMA 都是因果的）。
- 前向收益只在 `t + h < len(该股序列)` 时计入；股票停止交易后不补价。
- 每季度基线只用**同季度**数据；新上市股票在上市前不产生任何信号，也不进基线。
- 复权因子由该股**全历史**推得（启发式识别大除权），不使用任何未来外部数据。

## 用法

    # 烟囱测试（前 200 只）
    .venv/bin/python scripts/run_stage15.py --limit 200 --adjust forward

    # 主跑（前复权，沪深，分块落盘可续跑）
    .venv/bin/python scripts/run_stage15.py --adjust forward --chunk-symbols 500 --resume \
        --out data/stage15_forward_hs.json

    # 对照跑（未复权）
    .venv/bin/python scripts/run_stage15.py --adjust none --chunk-symbols 500 --resume \
        --out data/stage15_none_hs.json

    # 含北交所（稳健性对照）
    .venv/bin/python scripts/run_stage15.py --adjust forward --universe all \
        --out data/stage15_forward_all.json

    # 与阶段 14 的等价性回归
    .venv/bin/python scripts/run_stage15.py --verify-stage14
"""

from __future__ import annotations

import argparse
import gc
import json
import resource
import struct
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datasource.tdx.reader import (
    RECORD_SIZE,
    parse_day_file,
    resolve_hsjday_root,
    resolve_symbol_path,
)
from market.adjust import forward_adjust_frame
from strategies.filters import SymbolKind, classify_symbol, filter_for_kinds, kind_excluded

from scripts.pin30_common import pin30_series

# ---------------------------------------------------------------------------
# 常量（写死口径，不做隐式漂移）
# ---------------------------------------------------------------------------

PERIOD_START = date(2020, 1, 1)
PERIOD_END = date(2026, 8, 28)      # 本地 hsjday 数据末日

HOLDS = (20, 25, 60)
SHORT_PIN = 30.0
SHORT_PIN_TIGHT = 20.0
LONG_DEEP_MAX = 55.0                # 深水：长期随机 <= 55
LONG_ORIG_MIN = 80.0                # 原始单针：长期随机 >= 80
MIN_HIST_BARS = 120                 # 信号日/基线日要求的最少前置 K 线（覆盖 MA114）
MIN_N_QUARTER = 100                 # 季度样本量下限（低于此标注「样本不足」）

RULES = ("deep30", "deep20", "orig")
RULE_NAMES = {
    "deep30": "深水单针 短<=30",
    "deep20": "深水单针 短<=20",
    "orig": "原始单针 趋势多头+长>=80",
}

# 季报披露窗口（A 股法定披露期）：4 月底年报+一季报、8 月底半年报、10 月底三季报
DISCLOSURE_WINDOWS_MD = ((4, 1, 4, 30), (8, 1, 8, 31), (10, 1, 10, 31))
EARN_GROUPS = ("pre", "in", "post", "other")
EARN_NAMES = {"pre": "窗口前", "in": "窗口内", "post": "窗口后", "other": "其他"}
N_EG = len(EARN_GROUPS)

# 指数（市场环境标签）
INDEX_HS300 = "sh000300"
INDEX_SSE = "sh000001"


def peak_rss_mb() -> float:
    v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return v / (1024 * 1024) if sys.platform == "darwin" else v / 1024


# ---------------------------------------------------------------------------
# 季度网格
# ---------------------------------------------------------------------------


def build_quarters() -> list[dict]:
    """2020Q1 ~ 2026Q3（末季截到数据末日 2026-08-28），返回 27 个季度。"""
    out: list[dict] = []
    for year in range(PERIOD_START.year, PERIOD_END.year + 1):
        for q, (m0, m1) in enumerate(((1, 3), (4, 6), (7, 9), (10, 12)), start=1):
            qs = date(year, m0, 1)
            qe = date(year, m1, 31) if m1 in (3, 12) else date(year, m1, 30)
            if qe < PERIOD_START or qs > PERIOD_END:
                continue
            out.append(
                {
                    "label": "%dQ%d" % (year, q),
                    "start": max(qs, PERIOD_START),
                    "end": min(qe, PERIOD_END),
                }
            )
    return out


QUARTERS = build_quarters()
N_Q = len(QUARTERS)
Q_LABELS = [q["label"] for q in QUARTERS]
_Q_START_ORD = np.array([q["start"].toordinal() for q in QUARTERS], dtype=np.int64)


def quarter_ids(ordinals: np.ndarray) -> np.ndarray:
    """把日期 ordinal 数组映射到季度下标（假定全部落在 [PERIOD_START, PERIOD_END]）。"""
    return np.searchsorted(_Q_START_ORD, ordinals, side="right") - 1


# ---------------------------------------------------------------------------
# 交易日历（用上证指数的实际交易日，不用节假日近似表）
# ---------------------------------------------------------------------------


def load_index_frame(root: Path, code: str) -> pd.DataFrame:
    market = "sh" if code.startswith("sh") else "sz"
    path = root / market / "lday" / ("%s.day" % code)
    return parse_day_file(path)


def build_calendar(root: Path) -> np.ndarray:
    """真实交易日 ordinal 数组（升序），取自上证指数日线在 [PERIOD_START, PERIOD_END] 的日期。"""
    df = load_index_frame(root, INDEX_SSE)
    ords = np.array([d.toordinal() for d in df["date"]], dtype=np.int64)
    lo = PERIOD_START.toordinal()
    hi = PERIOD_END.toordinal()
    return ords[(ords >= lo) & (ords <= hi)]


def build_earnings_labels(cal: np.ndarray, span: int) -> np.ndarray:
    """给每个交易日打季报窗口标签：0=前 span 交易日 / 1=窗口内 / 2=后 span 交易日 / 3=其他。

    重叠处理（span=20 时「8 月窗口后 20 日」与「10 月窗口前 20 日」在 9 月重叠）：
    **窗口内 > 窗口前 > 窗口后**，即 9 月重叠段归「10 月窗口前」。span=10 时不重叠。
    """
    n = len(cal)
    lab = np.full(n, 3, dtype=np.int8)
    years = sorted({date.fromordinal(int(o)).year for o in cal})
    wins: list[tuple[int, int]] = []
    for y in years:
        for m0, d0, m1, d1 in DISCLOSURE_WINDOWS_MD:
            wins.append((date(y, m0, d0).toordinal(), date(y, m1, d1).toordinal()))
    # 先打「窗口后」，再打「窗口前」覆盖它，最后打「窗口内」覆盖两者
    for tag in (2, 0, 1):
        for w0, w1 in wins:
            i0 = int(np.searchsorted(cal, w0, side="left"))
            i1 = int(np.searchsorted(cal, w1, side="right"))  # [i0, i1) = 窗口内
            if tag == 1:
                lab[i0:i1] = 1
            elif tag == 0:
                lab[max(0, i0 - span) : i0] = 0
            else:
                lab[i1 : min(n, i1 + span)] = 2
    return lab


# ---------------------------------------------------------------------------
# 宇宙枚举
# ---------------------------------------------------------------------------


def list_stock_symbols(root: Path, universe: str) -> list[tuple[str, int, int, int]]:
    """枚举个股 .day 文件，返回 (code, n_bars, first_yyyymmdd, last_yyyymmdd)。

    universe: "hs" = 沪深（排除北交所）；"all" = 含北交所。
    只读文件头尾 4 字节，不解析全文件。
    """
    cfg = filter_for_kinds((SymbolKind.STOCK,))
    markets = ("sh", "sz") if universe == "hs" else ("sh", "sz", "bj")
    out: list[tuple[str, int, int, int]] = []
    for market in markets:
        lday = root / market / "lday"
        if not lday.is_dir():
            continue
        for fn in sorted(lday.iterdir()):
            if not fn.name.endswith(".day"):
                continue
            code = fn.name[2:8]
            if len(code) != 6:
                continue
            if kind_excluded(classify_symbol(market, code), cfg):
                continue
            nbars = fn.stat().st_size // RECORD_SIZE
            if nbars < MIN_HIST_BARS:
                continue
            with open(fn, "rb") as f:
                first = struct.unpack("<I", f.read(4))[0]
                f.seek((nbars - 1) * RECORD_SIZE)
                last = struct.unpack("<I", f.read(4))[0]
            out.append((code, nbars, first, last))
    return out


# ---------------------------------------------------------------------------
# 累加器（全部是 (N_Q * N_EG,) 的 float64 向量，bincount 直接加）
# ---------------------------------------------------------------------------

_CELLS = N_Q * N_EG


class Accum:
    """季度 × 季报窗口 的累加器组。

    每个 (rule, hold) 一份；baseline 也用同结构（一份 per hold）。
    字段：n / win / sum_ret / sum_mae / sum_mfe。
    """

    __slots__ = ("n", "win", "sum_ret", "sum_mae", "sum_mfe")

    def __init__(self) -> None:
        self.n = np.zeros(_CELLS, dtype=np.float64)
        self.win = np.zeros(_CELLS, dtype=np.float64)
        self.sum_ret = np.zeros(_CELLS, dtype=np.float64)
        self.sum_mae = np.zeros(_CELLS, dtype=np.float64)
        self.sum_mfe = np.zeros(_CELLS, dtype=np.float64)

    def add(self, cid: np.ndarray, ret: np.ndarray, mae: np.ndarray | None,
            mfe: np.ndarray | None) -> None:
        if cid.size == 0:
            return
        self.n += np.bincount(cid, minlength=_CELLS)
        self.win += np.bincount(cid, weights=(ret > 0).astype(np.float64), minlength=_CELLS)
        self.sum_ret += np.bincount(cid, weights=ret, minlength=_CELLS)
        if mae is not None:
            self.sum_mae += np.bincount(cid, weights=mae, minlength=_CELLS)
        if mfe is not None:
            self.sum_mfe += np.bincount(cid, weights=mfe, minlength=_CELLS)

    def to_json(self) -> dict:
        return {
            "n": self.n.tolist(),
            "win": self.win.tolist(),
            "sum_ret": self.sum_ret.tolist(),
            "sum_mae": self.sum_mae.tolist(),
            "sum_mfe": self.sum_mfe.tolist(),
        }

    @classmethod
    def from_json(cls, d: dict) -> "Accum":
        a = cls()
        a.n = np.asarray(d["n"], dtype=np.float64)
        a.win = np.asarray(d["win"], dtype=np.float64)
        a.sum_ret = np.asarray(d["sum_ret"], dtype=np.float64)
        a.sum_mae = np.asarray(d["sum_mae"], dtype=np.float64)
        a.sum_mfe = np.asarray(d["sum_mfe"], dtype=np.float64)
        return a


class State:
    """一次跑的全部累加状态（支持分块落盘 / 续跑）。"""

    def __init__(self) -> None:
        # 主累加：rule -> hold -> Accum（季报窗口 span=20 的分组）
        self.rule: dict[str, dict[int, Accum]] = {
            r: {h: Accum() for h in HOLDS} for r in RULES
        }
        # 基线：hold -> Accum（同宇宙同约束的全部股票-日）
        self.base: dict[int, Accum] = {h: Accum() for h in HOLDS}
        # span=10 的季报窗口分组（稳健性对照，只累加 n/win/sum_ret）
        self.rule10: dict[str, dict[int, Accum]] = {
            r: {h: Accum() for h in HOLDS} for r in RULES
        }
        self.base10: dict[int, Accum] = {h: Accum() for h in HOLDS}
        # 每季度「有有效数据的股票数」（幸存者偏差量化）
        self.sym_per_q = np.zeros(N_Q, dtype=np.int64)
        self.done: list[str] = []
        self.n_skipped = 0

    def to_json(self) -> dict:
        return {
            "rule": {r: {str(h): self.rule[r][h].to_json() for h in HOLDS} for r in RULES},
            "base": {str(h): self.base[h].to_json() for h in HOLDS},
            "rule10": {r: {str(h): self.rule10[r][h].to_json() for h in HOLDS} for r in RULES},
            "base10": {str(h): self.base10[h].to_json() for h in HOLDS},
            "sym_per_q": self.sym_per_q.tolist(),
            "done": self.done,
            "n_skipped": self.n_skipped,
        }

    @classmethod
    def from_json(cls, d: dict) -> "State":
        s = cls()
        for r in RULES:
            for h in HOLDS:
                s.rule[r][h] = Accum.from_json(d["rule"][r][str(h)])
                s.rule10[r][h] = Accum.from_json(d["rule10"][r][str(h)])
        for h in HOLDS:
            s.base[h] = Accum.from_json(d["base"][str(h)])
            s.base10[h] = Accum.from_json(d["base10"][str(h)])
        s.sym_per_q = np.asarray(d["sym_per_q"], dtype=np.int64)
        s.done = list(d["done"])
        s.n_skipped = int(d.get("n_skipped", 0))
        return s


# ---------------------------------------------------------------------------
# 单只股票的处理（核心）
# ---------------------------------------------------------------------------


def rolling_fwd_extremes(low: np.ndarray, high: np.ndarray, h: int) -> tuple[np.ndarray, np.ndarray]:
    """位置 i 上给出 min(low[i+1..i+h]) 与 max(high[i+1..i+h])（不足则 NaN）。

    `rolling(h).min()` 在位置 j = min(low[j-h+1..j])；`shift(-h)` 把它挪到位置 j-h，
    于是位置 i 拿到的正是 low[i+1..i+h] 的最小值。**只用未来 h 根**，用于事后统计
    MAE/MFE（不参与任何入场判定），无前视问题。
    """
    lo = pd.Series(low).rolling(h).min().shift(-h).to_numpy(dtype=float)
    hi = pd.Series(high).rolling(h).max().shift(-h).to_numpy(dtype=float)
    return lo, hi


def process_frame(
    df: pd.DataFrame,
    st: State,
    cal: np.ndarray,
    earn20: np.ndarray,
    earn10: np.ndarray,
    start_ord: int,
    end_ord: int,
    min_hist: int = MIN_HIST_BARS,
) -> int:
    """把单只股票的全历史帧累加进 State，返回本股贡献的有效基线日数。

    步骤：算指标 → 定位区间 [i0, i1) → 逐 hold 向量化前向收益 → bincount 到季度格子。
    """
    n = len(df)
    if n < min_hist + 1:
        return 0

    s = pin30_series(df)
    close = s["close"]
    short = s["short"]
    long_ = s["long"]
    trend = s["trend"]
    low = df["low"].astype(float).to_numpy()
    high = df["high"].astype(float).to_numpy()

    ordinals = np.fromiter((d.toordinal() for d in df["date"]), dtype=np.int64, count=n)
    i0 = int(np.searchsorted(ordinals, start_ord, side="left"))
    i1 = int(np.searchsorted(ordinals, end_ord, side="right"))
    i0 = max(i0, min_hist)          # 要求至少 min_hist 根前置 K 线
    if i1 - i0 < 1:
        return 0

    idx = np.arange(i0, i1, dtype=np.int64)
    ords = ordinals[i0:i1]
    qid = quarter_ids(ords)
    ok_q = (qid >= 0) & (qid < N_Q)

    # 季报窗口标签：本股日期在真实交易日历里的位置（对不上的归「其他」）
    pos = np.searchsorted(cal, ords, side="left")
    pos_c = np.clip(pos, 0, len(cal) - 1)
    hit = cal[pos_c] == ords
    eg20 = np.where(hit, earn20[pos_c], 3).astype(np.int64)
    eg10 = np.where(hit, earn10[pos_c], 3).astype(np.int64)

    base_c = close[idx]
    ok_price = base_c > 0
    ok0 = ok_q & ok_price

    # 规则掩码（只用 t 及更早的信息）
    not_trend = ~trend[idx]
    m_deep30 = not_trend & (short[idx] <= SHORT_PIN) & (long_[idx] <= LONG_DEEP_MAX)
    m_deep20 = not_trend & (short[idx] <= SHORT_PIN_TIGHT) & (long_[idx] <= LONG_DEEP_MAX)
    m_orig = trend[idx] & (short[idx] <= SHORT_PIN) & (long_[idx] >= LONG_ORIG_MIN)
    masks = {"deep30": m_deep30, "deep20": m_deep20, "orig": m_orig}

    cid20_all = qid * N_EG + eg20
    cid10_all = qid * N_EG + eg10

    n_base_days = 0
    for h in HOLDS:
        fmin, fmax = rolling_fwd_extremes(low, high, h)
        j = idx + h
        okh = ok0 & (j < n)
        if not okh.any():
            continue
        jj = j[okh]
        bc = base_c[okh]
        ret = close[jj] / bc - 1.0
        mae = fmin[idx[okh]] / bc - 1.0
        mfe = fmax[idx[okh]] / bc - 1.0
        c20 = cid20_all[okh]
        c10 = cid10_all[okh]
        st.base[h].add(c20, ret, mae, mfe)
        st.base10[h].add(c10, ret, None, None)
        if h == HOLDS[0]:
            n_base_days = int(okh.sum())
        sub = {}
        for rule, m in masks.items():
            mm = m[okh]
            if not mm.any():
                continue
            sub[rule] = mm
            st.rule[rule][h].add(c20[mm], ret[mm], mae[mm], mfe[mm])
            st.rule10[rule][h].add(c10[mm], ret[mm], None, None)

    # 幸存者偏差：本股在哪些季度有有效数据（用最短 hold 的有效日判定）
    j0 = idx + HOLDS[0]
    ok_short = ok0 & (j0 < n)
    if ok_short.any():
        st.sym_per_q[np.unique(qid[ok_short])] += 1
    return n_base_days


# ---------------------------------------------------------------------------
# 主扫描
# ---------------------------------------------------------------------------


def run_scan(args) -> dict:
    root = resolve_hsjday_root()
    cal = build_calendar(root)
    earn20 = build_earnings_labels(cal, 20)
    earn10 = build_earnings_labels(cal, 10)
    print("交易日历 %d 天（%s ~ %s）" % (
        len(cal), date.fromordinal(int(cal[0])), date.fromordinal(int(cal[-1]))), flush=True)
    import collections
    print("  季报窗口分组(span=20) 交易日数：%s" % dict(
        collections.Counter(EARN_GROUPS[int(x)] for x in earn20)), flush=True)
    print("  季报窗口分组(span=10) 交易日数：%s" % dict(
        collections.Counter(EARN_GROUPS[int(x)] for x in earn10)), flush=True)

    files = list_stock_symbols(root, args.universe)
    symbols = [f[0] for f in files]
    meta = {f[0]: {"bars": f[1], "first": f[2], "last": f[3]} for f in files}
    if args.limit:
        symbols = symbols[: args.limit]
    print("宇宙 %s：个股 %d 只" % (args.universe, len(symbols)), flush=True)

    partial = Path(args.partial or (str(Path(args.out).with_suffix("")) + "_partial.json"))
    st = State()
    if args.resume and partial.exists():
        st = State.from_json(json.loads(partial.read_text(encoding="utf-8")))
        print("  续跑：已完成 %d 只" % len(st.done), flush=True)
    done = set(st.done)

    start_ord = PERIOD_START.toordinal()
    end_ord = PERIOD_END.toordinal()
    todo = [s for s in symbols if s not in done]
    t0 = time.time()
    n_done = 0
    for i in range(0, len(todo), args.chunk_symbols):
        chunk = todo[i : i + args.chunk_symbols]
        for code in chunk:
            try:
                df = parse_day_file(resolve_symbol_path(root, code))
            except FileNotFoundError:
                st.n_skipped += 1
                st.done.append(code)
                continue
            if len(df) < MIN_HIST_BARS + 1:
                st.n_skipped += 1
                st.done.append(code)
                continue
            if args.adjust == "forward":
                df = forward_adjust_frame(df, code)
            process_frame(df, st, cal, earn20, earn10, start_ord, end_ord)
            st.done.append(code)
            n_done += 1
            del df
        gc.collect()
        partial.write_text(json.dumps(st.to_json(), ensure_ascii=False), encoding="utf-8")
        el = time.time() - t0
        print("  ...%d/%d 只（本次 %d），%.1fs，RSS峰值 %.0fMB" % (
            len(st.done), len(symbols), n_done, el, peak_rss_mb()), flush=True)

    print("扫描完成：%d 只，跳过 %d，%.1fs" % (n_done, st.n_skipped, time.time() - t0), flush=True)
    out = {
        "meta": {
            "adjust": args.adjust,
            "universe": args.universe,
            "period": [str(PERIOD_START), str(PERIOD_END)],
            "holds": list(HOLDS),
            "quarters": Q_LABELS,
            "min_hist_bars": MIN_HIST_BARS,
            "n_symbols_universe": len(symbols),
            "n_symbols_processed": len(st.done) - st.n_skipped,
            "n_skipped": st.n_skipped,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "state": st.to_json(),
        "file_meta": meta,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("已写入 %s" % args.out, flush=True)
    return out


# ---------------------------------------------------------------------------
# 阶段 14 等价性回归
# ---------------------------------------------------------------------------


def verify_stage14(limit: int | None = None) -> None:
    """用阶段 14 的 load_universe 加载四段窗口，跑本脚本的向量化累加，对齐组1 数字。

    阶段 14 是**未复权**、尾部 lookback 根、含北交所、带停牌过滤的口径，这里逐条照抄，
    只把「逐日 Python 循环」换成「向量化 bincount」。数字对齐 = 本脚本的收益/胜率/
    基线计算与阶段 14 等价。
    """
    from market.calendar import trading_days
    from scripts.run_oos_strategies import WINDOWS, WINDOW_LABELS, load_universe
    from backtest.baseline import compute_baseline

    ref = json.loads((ROOT / "data" / "stage14_backtest.json").read_text(encoding="utf-8"))
    print("=" * 100)
    print("阶段 14 等价性回归（组1 纯深水单针，未复权，25/60 日）")
    print("=" * 100)
    print("%-8s %-6s %10s %10s %12s %12s %12s %12s" % (
        "段", "持有", "n(本)", "n(14)", "胜率(本)", "胜率(14)", "收益(本)", "收益(14)"))
    max_dev = 0.0
    for wkey in ("IS", "A", "B", "C"):
        label = WINDOW_LABELS[wkey]
        start, end = (date.fromisoformat(x) for x in WINDOWS[wkey])
        days = trading_days(start, end)
        lookback = len(days) + 320
        candles, _ = load_universe(end, lookback, kinds=(SymbolKind.STOCK,))
        syms = sorted(candles)
        if limit:
            syms = syms[:limit]
        so, eo = start.toordinal(), end.toordinal()
        acc = {h: {"n": 0, "win": 0, "sum": 0.0} for h in (25, 60)}
        for code in syms:
            df = candles[code]
            nn = len(df)
            if nn < 200:
                continue
            s = pin30_series(df)
            close, short, long_, trend = s["close"], s["short"], s["long"], s["trend"]
            ords = np.fromiter((d.toordinal() for d in df["date"]), dtype=np.int64, count=nn)
            i0 = int(np.searchsorted(ords, so, side="left"))
            i1 = int(np.searchsorted(ords, eo, side="right"))
            if i1 - i0 < 2:
                continue
            idx = np.arange(i0, i1, dtype=np.int64)
            m = (~trend[idx]) & (short[idx] <= SHORT_PIN) & (long_[idx] <= LONG_DEEP_MAX)
            m &= (idx + 1) < nn          # 阶段 14 的 t+1<n 条件
            for h in (25, 60):
                sel = idx[m & ((idx + h) < nn)]
                if sel.size == 0:
                    continue
                r = close[sel + h] / close[sel] - 1.0
                acc[h]["n"] += int(sel.size)
                acc[h]["win"] += int((r > 0).sum())
                acc[h]["sum"] += float(r.sum())
        base = compute_baseline(candles, syms, "stock", start, end, [25, 60])
        bl = {h.hold_days: (h.win_rate, h.avg_return) for h in base.holds}
        for h in (25, 60):
            a = acc[h]
            wr = a["win"] / a["n"] if a["n"] else 0.0
            av = a["sum"] / a["n"] if a["n"] else 0.0
            r14 = ref[label]["g1"][str(h)]
            print("%-8s %-6d %10d %10d %11.4f %11.4f %11.5f %11.5f" % (
                label, h, a["n"], r14["n"], wr, r14["win_rate"], av, r14["avg_return"]))
            b14 = ref[label]["baselines"][str(h)]
            print("%-8s %-6s 基线胜率 本=%.5f / 14=%.5f  基线收益 本=%.5f / 14=%.5f" % (
                "", "", bl[h][0], b14["win_rate"], bl[h][1], b14["avg_return"]))
            max_dev = max(max_dev, abs(wr - r14["win_rate"]), abs(av - r14["avg_return"]),
                          abs(bl[h][0] - b14["win_rate"]), abs(bl[h][1] - b14["avg_return"]))
        del candles
        gc.collect()
    print("\n最大偏差（胜率/收益，绝对值）= %.6f" % max_dev)
    print("判定：%s" % ("等价 ✅" if max_dev < 5e-4 else "有偏差，需排查 ❌"))


def main() -> None:
    ap = argparse.ArgumentParser(description="阶段15 深水单针 27 季度滚动验证")
    ap.add_argument("--adjust", choices=("forward", "none"), default="forward")
    ap.add_argument("--universe", choices=("hs", "all"), default="hs")
    ap.add_argument("--out", default=None)
    ap.add_argument("--partial", default=None)
    ap.add_argument("--chunk-symbols", type=int, default=500)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--verify-stage14", action="store_true")
    ap.add_argument("--verify-limit", type=int, default=None)
    args = ap.parse_args()

    if args.verify_stage14:
        verify_stage14(limit=args.verify_limit)
        return

    if args.out is None:
        args.out = "data/stage15_%s_%s.json" % (args.adjust, args.universe)
    run_scan(args)


if __name__ == "__main__":
    main()
