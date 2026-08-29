#!/usr/bin/env python3
"""阶段 11 第 2 段：regime 决定选股池 —— 四段回测核心。

口径（详见 docs/阶段11-报告.md 与任务书）：
  - 全市场等权基准 = 沪深 A 股个股（sh 60/68、sz 00/30，剔除指数/ETF/债券/B股）
    等权日收益的累乘指数。
  - 高股息篮子 = 银行(东财BK1283 全部) + 煤炭(BK0437) + 电力(BK0428)
    + 公用事业(BK0427) + 高速公路(BK1483) + 福耀玻璃(600660) + 格力电器(000651)，
    成分股等权。
  - 资金流入篮子 = 每个交易日按「板块 20 日相对强度(vs 全市场等权) 降序」，
    且「板块成交额占全市场比重 20 日变化 > 0」过滤后取前 N=5 个板块，
    板块等权（每板块 1/N，板块内成分股等权）。
  - regime 用上证指数 20 日涨跌，主口径大涨≥+2% / 大跌≤-2%（见阈值敏感性）。
  - 切换滞后：T 日收盘确认 regime，T+1 日才换仓；前向收益从 T+1 收盘起算。

内存纪律：流式遍历 .day 文件（numpy frombuffer 向量化），不物化全市场 DataFrame；
只积累市场/板块/篮子的逐日 (收益和, 计数, 成交额)，峰值 O(1)。

用法（仓库根目录）：
    .venv/bin/python scripts/run_regime_basket_backtest.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HSJDAY = Path.home() / "Desktop" / "每日复盘" / "hsjday"

UP_TH = 0.02
DOWN_TH = -0.02
LOOKBACK = 20
TOP_N = 5
HORIZONS = (20, 60)
MIN_MARKET_SYMBOLS = 50

WINDOWS: list[tuple[str, str, str]] = [
    ("IS", "2026-03-01", "2026-08-27"),
    ("OOS-A", "2023-01-01", "2023-12-31"),
    ("OOS-B", "2024-01-01", "2024-12-31"),
    ("OOS-C", "2025-01-01", "2026-02-28"),
]

OUT = DATA / "regime_basket_backtest.json"

# 高股息篮子成分：银行 + 煤炭 + 公用事业(含电力/燃气/水务) + 高速公路 板块代码 + 点名股
DEFENSIVE_SECTOR_CODES = ("BK1283", "BK0437", "BK0427", "BK1483")
NAMED_STOCKS = ("600660", "000651")  # 福耀玻璃, 格力电器

# 资金流入排名宇宙：剔除与父板块重叠的二级板块（避免成交额占比双计）
#   电力(BK0428) ⊂ 公用事业(BK0427)；高速公路(BK1483) ⊂ 交通运输(BK1210)
EXCLUDED_FROM_UNIVERSE = {"BK0428", "BK1483"}


def load_sector_members() -> tuple[dict[str, str], dict[str, dict]]:
    d = json.loads((DATA / "sector_members.json").read_text())
    sym2sector: dict[str, str] = {}
    sectors: dict[str, dict] = {}
    for code, info in d["sectors"].items():
        sectors[code] = info
        if info.get("error"):
            continue
        for m in info["members"]:
            sym2sector[m["code"]] = code
    return sym2sector, sectors


def is_stock_sh(sym: str) -> bool:
    return sym[:2] in ("60", "68")


def is_stock_sz(sym: str) -> bool:
    return sym[:2] in ("00", "30")


def iter_stock_files():
    """遍历沪深 A 股个股 .day 文件，yield (symbol, path)。"""
    for market, pred in (("sh", is_stock_sh), ("sz", is_stock_sz)):
        lday = HSJDAY / market / "lday"
        if not lday.exists():
            continue
        for f in lday.iterdir():
            if not f.name.endswith(".day"):
                continue
            sym = f.name[len(market):-4]
            if pred(sym):
                yield sym, f


def parse_returns_amount(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """返回 (dates_int, daily_ret, amount)，向量化解析。

    daily_ret[i] 对应 dates[i] 的当日收益（close[i]/close[i-1]-1），长度 = len-1。
    amount[i] 对应 dates[i] 的成交额。
    """
    raw = path.read_bytes()
    n = len(raw) // 32
    if n < 2:
        return np.empty(0, np.int64), np.empty(0, np.float64), np.empty(0, np.float64)
    dt = np.dtype([
        ("date", "<u4"), ("open", "<u4"), ("high", "<u4"), ("low", "<u4"),
        ("close", "<u4"), ("amount", "<f4"), ("volume", "<u4"), ("res", "<u4"),
    ])
    arr = np.frombuffer(raw[: n * 32], dtype=dt)
    dates = arr["date"].astype(np.int64)
    close = arr["close"].astype(np.float64) / 100.0
    amount = arr["amount"].astype(np.float64)
    ret = np.empty(len(close) - 1, np.float64)
    np.divide(close[1:], close[:-1], out=ret, where=close[:-1] != 0)
    ret[close[:-1] == 0] = 0.0
    ret -= 1.0
    return dates[1:], ret, amount[1:]


def classify(r20: float) -> str:
    if r20 >= UP_TH:
        return "大涨"
    if r20 <= DOWN_TH:
        return "大跌"
    return "中性"


def build_index_series(agg: dict[int, list[float]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """agg: date_int -> [ret_sum, count, amount_sum]。返回对齐 index_dates 的 (ret, amount, count)。"""
    dates = np.array(sorted(agg), dtype=np.int64)
    rs = np.array([agg[d][0] for d in dates], np.float64)
    amt = np.array([agg[d][2] for d in dates], np.float64)
    cnt = np.array([agg[d][1] for d in dates], np.float64)
    s = pd.Series(rs, index=pd.Index(dates, name="date"))
    return s, amt, cnt, dates


def main() -> None:
    sym2sector, sectors = load_sector_members()

    # 高股息篮子成员集合（含各板块全部成员 + 点名股）
    defensive_members: set[str] = set(NAMED_STOCKS)
    for code in DEFENSIVE_SECTOR_CODES:
        for m in sectors.get(code, {}).get("members", []):
            defensive_members.add(m["code"])

    # 上证指数 regime
    idx_path = HSJDAY / "sh" / "lday" / "sh000001.day"
    raw = idx_path.read_bytes()
    n = len(raw) // 32
    dt = np.dtype([("date", "<u4"), ("open", "<u4"), ("high", "<u4"), ("low", "<u4"),
                   ("close", "<u4"), ("amount", "<f4"), ("volume", "<u4"), ("res", "<u4")])
    idxarr = np.frombuffer(raw[: n * 32], dtype=dt)
    idx_dates_all = idxarr["date"].astype(np.int64)
    idx_close_all = idxarr["close"].astype(np.float64) / 100.0

    # 截取输出窗口 [20221201, 20260827]，并往前留 20 日算 r20
    full_dates = idx_dates_all
    full_close = idx_close_all
    lo, hi = 20221201, 20260827
    mask = (full_dates >= lo) & (full_dates <= hi)
    w_dates = full_dates[mask]
    w_close = full_close[mask]
    r20 = pd.Series(w_close).pct_change(LOOKBACK).to_numpy()
    regime = np.array([classify(float(x)) if x == x else "中性" for x in r20])

    index_dates = w_dates  # 交易日历锚点
    N_DAYS = len(index_dates)
    date_to_pos = {int(d): i for i, d in enumerate(index_dates)}

    # 市场 / 板块 / 篮子 聚合
    mkt_agg: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    sec_agg: dict[str, dict[int, list[float]]] = {c: defaultdict(lambda: [0.0, 0.0, 0.0]) for c in sectors if not sectors[c].get("error")}
    def_agg: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])

    n_seen = 0
    for sym, f in iter_stock_files():
        try:
            dts, ret, amt = parse_returns_amount(f)
        except Exception:  # noqa: BLE001
            continue
        if len(dts) == 0:
            continue
        n_seen += 1
        sector = sym2sector.get(sym)
        is_def = sym in defensive_members
        for i in range(len(dts)):
            d = int(dts[i])
            r = float(ret[i])
            a = float(amt[i])
            if not (r == r) or not (a == a):  # NaN 守卫
                continue
            cell = mkt_agg[d]
            cell[0] += r
            cell[1] += 1.0
            cell[2] += a
            if sector is not None:
                sc = sec_agg[sector][d]
                sc[0] += r
                sc[1] += 1.0
                sc[2] += a
            if is_def:
                dc = def_agg[d]
                dc[0] += r
                dc[1] += 1.0
                dc[2] += a

    print(f"扫描个股数: {n_seen}", file=sys.stderr)

    def agg_to_aligned(agg):
        s = pd.Series(dtype=np.float64)
        for d, (rs, cnt, amt) in agg.items():
            if cnt >= 1:
                s[d] = rs / cnt
        s = s.reindex(pd.Index(index_dates, name="date")).fillna(0.0)
        return s.to_numpy()

    def agg_amount_aligned(agg):
        s = pd.Series(dtype=np.float64)
        for d, (rs, cnt, amt) in agg.items():
            s[d] = amt
        s = s.reindex(pd.Index(index_dates, name="date")).fillna(0.0)
        return s.to_numpy()

    mret = agg_to_aligned(mkt_agg)
    mamt = agg_amount_aligned(mkt_agg)
    bret = agg_to_aligned(def_agg)
    sret = {c: agg_to_aligned(sec_agg[c]) for c in sec_agg}
    samt = {c: agg_amount_aligned(sec_agg[c]) for c in sec_agg}

    # 指数级别（累乘）
    def levels(r):
        return np.cumprod(1.0 + r)

    midx = levels(mret)
    bidx = levels(bret)
    sidx = {c: levels(sret[c]) for c in sec_agg}

    # 20 日涨跌（级别 pct_change 20）
    def ret20(lv):
        out = np.full(len(lv), np.nan)
        out[LOOKBACK:] = lv[LOOKBACK:] / lv[:-LOOKBACK] - 1.0
        return out

    mr20 = ret20(midx)
    sr20 = {c: ret20(sidx[c]) for c in sec_agg}

    # 成交额占比及 20 日变化
    share = {c: samt[c] / np.where(mamt > 0, mamt, np.nan) for c in sec_agg}
    share_chg = {}
    for c in sec_agg:
        sh = share[c]
        chg = np.full(len(sh), np.nan)
        chg[LOOKBACK:] = sh[LOOKBACK:] - sh[:-LOOKBACK]
        share_chg[c] = chg

    # 相对强度 = 板块 20 日涨跌 - 市场 20 日涨跌
    rel = {c: sr20[c] - mr20 for c in sec_agg}

    sector_codes = sorted(c for c in sec_agg if c not in EXCLUDED_FROM_UNIVERSE)

    def top_sectors_at(pos: int, n: int = TOP_N) -> list[str]:
        """pos 为「数据截至 pos 日」，选资金流入板块：相对强度降序 + 成交额占比 20 日变化>0。"""
        cand = []
        for c in sector_codes:
            r = rel[c][pos]
            ch = share_chg[c][pos]
            if r is None or (isinstance(r, float) and np.isnan(r)):
                continue
            if ch is not None and not np.isnan(ch) and ch > 0:
                cand.append((r, c))
        cand.sort(key=lambda x: -x[0])
        return [c for _, c in cand[:n]]

    def fwd(pos_entry: int, h: int, lv: np.ndarray) -> float:
        """从 entry 位置持有 h 个交易日的前向收益；越界返回 NaN。"""
        j = pos_entry + h
        if j >= N_DAYS or lv[pos_entry] <= 0:
            return float("nan")
        return float(lv[j] / lv[pos_entry] - 1.0)

    # ── 回测：四段 × regime 桶 × 篮子 前向 20/60 收益（绝对 + 超额）──
    results: dict = {"periods": {}, "pooled": {}, "strategy": {}}

    # 预计算每个交易日的「资金流入篮子前向收益」需要逐日 top-N，但前向收益按 entry 位置算。
    # 为 Q1/Q2 逐日记录，我们在循环里现算。

    for label, s, e in WINDOWS:
        sd, ed = int(s.replace("-", "")), int(e.replace("-", ""))
        pos_in = [i for i, d in enumerate(index_dates) if sd <= d <= ed]
        bucket_days: dict[str, list[int]] = {"大涨": [], "中性": [], "大跌": []}
        for i in pos_in:
            if i < LOOKBACK:  # regime 需要 20 日历史
                continue
            bucket_days[regime[i]].append(i)
        period = {"range": f"{s}~{e}", "buckets": {}}
        for bucket, days in bucket_days.items():
            rec = {"n_days": len(days), "n_sample_flag": "样本不足(<100)，不作结论" if len(days) < 100 else "ok"}
            for h in HORIZONS:
                rows = {
                    "market": [], "defensive": [], "aggressive": [],
                }
                for i in days:
                    entry = i + 1  # 滞后：确认后下一交易日换仓
                    if entry >= N_DAYS:
                        continue
                    m = fwd(entry, h, midx)
                    b = fwd(entry, h, bidx)
                    rows["market"].append(m)
                    rows["defensive"].append(b)
                    # 资金流入篮子：top-N 板块等权前向
                    ts = top_sectors_at(i)
                    if ts:
                        vals = [fwd(entry, h, sidx[c]) for c in ts]
                        vals = [v for v in vals if v == v]
                        rows["aggressive"].append(float(np.mean(vals)) if vals else np.nan)
                    else:
                        rows["aggressive"].append(np.nan)
                sub = {}
                for k, v in rows.items():
                    v = np.array(v, np.float64)
                    v = v[~np.isnan(v)]
                    if len(v) == 0:
                        sub[k] = {"n": 0, "mean": None, "median": None}
                        continue
                    sub[k] = {"n": int(len(v)), "mean": round(float(np.mean(v)), 6), "median": round(float(np.median(v)), 6)}
                # 超额 = 篮子 - 市场（逐日对齐再平均）
                exc = {"defensive": [], "aggressive": []}
                for i in days:
                    entry = i + 1
                    if entry >= N_DAYS:
                        continue
                    m = fwd(entry, h, midx)
                    b = fwd(entry, h, bidx)
                    if m == m and b == b:
                        exc["defensive"].append(b - m)
                    ts = top_sectors_at(i)
                    if ts and m == m:
                        vals = [fwd(entry, h, sidx[c]) for c in ts]
                        vals = [v for v in vals if v == v]
                        if vals:
                            a = float(np.mean(vals))
                            exc["aggressive"].append(a - m)
                exc_out = {}
                for k, v in exc.items():
                    v = np.array(v, np.float64)
                    exc_out[k] = {"n": int(len(v)), "mean": round(float(np.mean(v)), 6) if len(v) else None}
                rec[f"fwd_{h}"] = {"absolute": sub, "excess_vs_market": exc_out}
            period["buckets"][bucket] = rec
        results["periods"][label] = period

    # ── 汇总（pooled）：IS 与 OOS 合并 ──
    for pool_label, wlabels in (("IS", ["IS"]), ("OOS", ["OOS-A", "OOS-B", "OOS-C"])):
        days: dict[str, list[int]] = {"大涨": [], "中性": [], "大跌": []}
        for wl in wlabels:
            sd = int(WINDOWS[[x[0] for x in WINDOWS].index(wl)][1].replace("-", ""))
            ed = int(WINDOWS[[x[0] for x in WINDOWS].index(wl)][2].replace("-", ""))
            for i, d in enumerate(index_dates):
                if sd <= d <= ed and i >= LOOKBACK:
                    days[regime[i]].append(i)
        pool = {}
        for bucket, dl in days.items():
            rec = {"n_days": len(dl), "n_sample_flag": "样本不足(<100)，不作结论" if len(dl) < 100 else "ok"}
            for h in HORIZONS:
                rows = {"market": [], "defensive": [], "aggressive": []}
                exc = {"defensive": [], "aggressive": []}
                for i in dl:
                    entry = i + 1
                    if entry >= N_DAYS:
                        continue
                    m = fwd(entry, h, midx)
                    b = fwd(entry, h, bidx)
                    if m == m:
                        rows["market"].append(m)
                    if b == b:
                        rows["defensive"].append(b)
                    if m == m and b == b:
                        exc["defensive"].append(b - m)
                    ts = top_sectors_at(i)
                    if ts:
                        vals = [fwd(entry, h, sidx[c]) for c in ts]
                        vals = [v for v in vals if v == v]
                        if vals and m == m:
                            a = float(np.mean(vals))
                            rows["aggressive"].append(a)
                            exc["aggressive"].append(a - m)
                sub = {}
                for k, v in rows.items():
                    v = np.array(v, np.float64)
                    v = v[~np.isnan(v)]
                    sub[k] = {"n": int(len(v)), "mean": round(float(np.mean(v)), 6) if len(v) else None, "median": round(float(np.median(v)), 6) if len(v) else None}
                exc_out = {}
                for k, v in exc.items():
                    v = np.array(v, np.float64)
                    exc_out[k] = {"n": int(len(v)), "mean": round(float(np.mean(v)), 6) if len(v) else None}
                rec[f"fwd_{h}"] = {"absolute": sub, "excess_vs_market": exc_out}
            pool[bucket] = rec
        results["pooled"][pool_label] = pool

    # ── Q3：换篮子 vs 单一篮子（累计收益，逐日，含滞后）──
    def strategy_daily_returns():
        """返回 {switch, always_defensive, always_aggressive, always_market} 的日收益数组。"""
        switch = np.full(N_DAYS, np.nan)
        always_agg = np.full(N_DAYS, np.nan)
        for i in range(1, N_DAYS):
            prev_regime = regime[i - 1]
            ts = top_sectors_at(i - 1)
            if ts:
                a = float(np.mean([sret[c][i] for c in ts]))
                always_agg[i] = a
            if prev_regime == "大涨" and ts:
                switch[i] = always_agg[i]
            elif prev_regime == "大跌":
                switch[i] = bret[i]
            else:  # 中性 → 市场
                switch[i] = mret[i]
        switch[0] = mret[0] if not np.isnan(mret[0]) else 0.0
        always_agg[0] = mret[0] if not np.isnan(mret[0]) else 0.0
        return {
            "switch": switch,
            "always_defensive": bret.copy(),
            "always_aggressive": always_agg,
            "always_market": mret.copy(),
        }

    daily = strategy_daily_returns()
    for label, s, e in WINDOWS:
        sd, ed = int(s.replace("-", "")), int(e.replace("-", ""))
        pos = [i for i, d in enumerate(index_dates) if sd <= d <= ed]
        seg = {}
        for k, r in daily.items():
            rr = r[pos]
            rr = rr[~np.isnan(rr)]
            if len(rr) == 0:
                seg[k] = {"n": 0, "cum_return": None}
            else:
                seg[k] = {"n": int(len(rr)), "cum_return": round(float(np.prod(1.0 + rr) - 1.0), 6)}
        results["strategy"][label] = seg
    # 全区间
    allseg = {}
    for k, r in daily.items():
        rr = r[~np.isnan(r)]
        allseg[k] = {"n": int(len(rr)), "cum_return": round(float(np.prod(1.0 + rr) - 1.0), 6)}
    results["strategy"]["ALL"] = allseg

    results["meta"] = {
        "up_th": UP_TH, "down_th": DOWN_TH, "lookback": LOOKBACK, "top_n": TOP_N,
        "horizons": list(HORIZONS),
        "n_stocks_scanned": n_seen,
        "n_sectors": len(sector_codes),
        "n_defensive_members": len(defensive_members),
        "n_days": N_DAYS,
        "lag": "确认后下一交易日换仓",
        "note": "行业成分为当前快照→幸存者偏差；绝对收益与超额收益分列",
    }
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"已落盘 {OUT}")

    # 落盘对齐后的数组供敏感性分析复用（避免重复流式扫描）
    np.savez_compressed(
        DATA / "regime_basket_arrays.npz",
        index_dates=index_dates.astype(np.int64),
        regime=regime,
        mret=mret, mamt=mamt, midx=midx, mr20=mr20,
        bret=bret, bidx=bidx,
        sector_codes=np.array(sector_codes),
        sret=np.vstack([sret[c] for c in sector_codes]),
        samt=np.vstack([samt[c] for c in sector_codes]),
        sidx=np.vstack([sidx[c] for c in sector_codes]),
        sr20=np.vstack([sr20[c] for c in sector_codes]),
        share_chg=np.vstack([share_chg[c] for c in sector_codes]),
    )
    print(f"已落盘 {DATA / 'regime_basket_arrays.npz'}")


if __name__ == "__main__":
    main()
