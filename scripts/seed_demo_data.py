#!/usr/bin/env python3
"""生成演示数据（data/demo_hsjday/）+ 概览页快照，让「没有真实数据也能跑」。

背景：面试官 clone 下来没有通达信 hsjday 数据。本脚本生成几十只虚构标的的
合成日线（随机游走 + 趋势），落成与真实 hsjday 完全一致的 ``.day`` 二进制，
再跑一遍回测引擎生成概览页快照。之后把 ``STOCK_HSJDAY_ROOT`` 指到这个目录，
整套平台（指标 / 选股 / 回测 / 调度 / 概览）都能体验。

用法（仓库根目录）：

    .venv/bin/python scripts/seed_demo_data.py
    STOCK_HSJDAY_ROOT="$PWD/data/demo_hsjday" .venv/bin/uvicorn main:app \
        --app-dir apps/api/src --port 8000

产物：
    data/demo_hsjday/                     演示日线（38 只，约 760 根/只）
    data/dashboard_snapshot.json          概览页快照（用演示数据算）
"""

from __future__ import annotations

import json
import os
import struct
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from market.calendar import trading_days

# 演示数据根目录（默认放仓库内 data/，.gitignore 已忽略 data/demo_hsjday）
DEMO_ROOT = ROOT / "data" / "demo_hsjday"
# 快照输出（与 API 默认读取路径一致）
SNAPSHOT_PATH = ROOT / "data" / "dashboard_snapshot.json"

# 合成日线截止日（与前端选股页默认日期一致，保证开箱即用）
END_DATE = date(2026, 8, 27)
N_BARS = 760  # 每只约 3 年日线，够月线共振（30 月 ≈ 660 日）+ 余量
SEED = 20260827

_REC = struct.Struct("<IIIIIfII")  # 与 datasource.tdx.reader 完全一致

# (代码, 走势形态)。形态决定随机游走的漂移与波动，覆盖涨/跌/震荡/深跌反弹。
# 前缀覆盖沪主板/科创板/深主板/创业板/北交所 + 沪深 ETF，保证五策略都有宇宙。
_SYMBOLS: list[tuple[str, str]] = [
    # 沪主板
    ("600519", "uptrend"), ("600036", "range"), ("600028", "range"),
    ("601318", "downtrend"), ("603288", "uptrend"), ("605499", "dip_recover"),
    ("600000", "range"), ("600016", "range"), ("600030", "uptrend"),
    ("601988", "downtrend"), ("603501", "dip_recover"), ("605358", "range"),
    # 科创板
    ("688981", "uptrend"), ("688111", "downtrend"),
    # 深主板 / 中小
    ("000001", "range"), ("000002", "range"), ("000858", "uptrend"),
    ("002415", "downtrend"), ("002594", "uptrend"), ("003816", "range"),
    ("000063", "uptrend"), ("002230", "dip_recover"), ("003000", "range"),
    # 创业板
    ("300750", "uptrend"), ("300059", "downtrend"), ("301236", "dip_recover"),
    # 北交所
    ("430017", "range"), ("830799", "uptrend"), ("870357", "range"), ("920002", "downtrend"),
    # 沪 ETF
    ("510300", "range"), ("510500", "range"), ("512880", "dip_recover"),
    ("588080", "downtrend"), ("588710", "etf_divergence"),
    # 深 ETF
    ("159919", "range"), ("159915", "uptrend"), ("159949", "dip_recover"),
]

# 各形态的 (日漂移, 日波动)。dip_recover 在随机游走基础上叠加一段深跌+反弹。
_PROFILE_DRIFT = {
    "uptrend": 0.0008,
    "range": 0.0000,
    "downtrend": -0.0008,
    "dip_recover": 0.0001,
}
_PROFILE_VOL = {
    "uptrend": 0.018,
    "range": 0.022,
    "downtrend": 0.020,
    "dip_recover": 0.024,
}


def resolve_market_dir(code: str) -> str:
    """按前缀返回市场目录（与真实 hsjday 的 sh/sz/bj 目录一致）。

    注意：这里比 datasource 的 resolve_market 多了 ETF 前缀处理——沪市 ETF
    （51x/56x/58x）在 sh、深市 ETF（159）在 sz，否则 ETF 会被错误归到 sz。
    """
    if code.startswith(("60", "68")):
        return "sh"
    if code.startswith(("43", "83", "87", "88", "92")):
        return "bj"
    if code.startswith(("510", "511", "512", "513", "515", "516", "517", "518", "520", "560", "561", "562", "563", "588")):
        return "sh"
    return "sz"


def _price_series(profile: str, n: int, rng: np.random.Generator) -> np.ndarray:
    """生成一条收盘价序列（随机游走 + 趋势，dip_recover 叠加深跌反弹）。

    etf_divergence 是手工构造的「跌 30% + 底背离」形态，保证演示数据里
    etf_accumulation 策略能真实触发（否则 ETF 太稀少，演示时该策略永远 0 信号）。
    """
    if profile == "etf_divergence":
        return _etf_divergence_series(n)

    drift = _PROFILE_DRIFT[profile]
    vol = _PROFILE_VOL[profile]

    if profile == "dip_recover":
        # 前半段温和随机游走，中段连跌约 30%，后半段反弹（触发超卖/底背离形态）
        base = 20.0
        returns = rng.normal(drift, vol, n)
        rets = np.zeros(n)
        for i in range(n):
            extra = 0.0
            if n * 0.35 <= i < n * 0.60:  # 中段深跌
                extra = -0.008
            elif i >= n * 0.60:  # 后半段反弹
                extra = +0.010
            rets[i] = returns[i] + extra
    else:
        rets = rng.normal(drift, vol, n)

    # 涨跌停粗约束（A股 ±10%，ETF ±10% 近似），避免极端值
    rets = np.clip(rets, -0.095, 0.095)

    price = np.empty(n)
    price[0] = float(rng.uniform(3.0, 60.0)) if profile != "dip_recover" else base
    price[0] = 20.0 if profile == "dip_recover" else price[0]
    for i in range(1, n):
        price[i] = price[i - 1] * (1.0 + rets[i])
    return np.maximum(price, 0.5)  # 兜底不为 0/负


def _etf_divergence_series(n: int) -> np.ndarray:
    """构造一只「跌 30% + 双底背离」的 ETF 日线（最后 60 根是关键形态）。

    形态：前段温和上升至 30 → 急跌 30%（第一低点 21）→ 反弹至 25 →
    二次回落到 20.5（第二低点）→ 温和回升至 21.5 → 最后一根小幅新低 20.45。
    这样「价格创 20 日新低、但 MACD/RSI 未同步新低」，触发底背离。
    """
    p = np.empty(n)
    head = n - 60
    for i in range(head):
        p[i] = 20.0 + 10.0 * (i / max(1, head - 1))  # 20 → 30 温和上升
    tail = np.empty(60)
    for j in range(60):
        if j <= 20:
            tail[j] = 30.0 - 9.0 * (j / 20)             # 30 → 21
        elif j <= 30:
            tail[j] = 21.0 + 4.0 * ((j - 20) / 10)      # 21 → 25
        elif j <= 40:
            tail[j] = 25.0 - 4.5 * ((j - 30) / 10)      # 25 → 20.5
        elif j <= 58:
            tail[j] = 20.5 + 1.0 * ((j - 40) / 18)      # 20.5 → 21.5 回升
        else:
            tail[j] = 20.45                              # 最后一根小幅新低
    p[head:] = tail
    return p


def _gen_symbol(code: str, profile: str, days: list[date], rng) -> list[dict]:
    """生成单只标的的 OHLCV 记录（date/open/high/low/close/volume/amount）。"""
    n = len(days)
    closes = _price_series(profile, n, rng)

    rows: list[dict] = []
    for i in range(n):
        close = float(closes[i])
        prev = float(closes[i - 1]) if i > 0 else close
        open_ = prev * (1.0 + float(rng.normal(0, 0.004)))
        high = max(open_, close) * (1.0 + abs(float(rng.normal(0, 0.006))))
        low = min(open_, close) * (1.0 - abs(float(rng.normal(0, 0.006))))
        volume = int(rng.uniform(8000, 400000))
        amount = close * volume * 100.0  # 1 手 = 100 股，金额 = 价 × 股数
        rows.append(
            {
                "date": days[i],
                "open": round(open_, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "volume": volume,
                "amount": round(amount, 2),
            }
        )
    return rows


def _write_day_file(path: Path, rows: list[dict]) -> None:
    """把记录写成一个 .day 文件（32 字节定长记录，与真实格式一致）。"""
    data = bytearray()
    for r in rows:
        data += _REC.pack(
            int(r["date"].strftime("%Y%m%d")),
            int(round(r["open"] * 100)),
            int(round(r["high"] * 100)),
            int(round(r["low"] * 100)),
            int(round(r["close"] * 100)),
            float(r["amount"]),
            int(r["volume"]),
            0,
        )
    path.write_bytes(bytes(data))


def generate_demo_data(demo_root: Path) -> list[date]:
    """生成演示 .day 文件，返回交易日列表。"""
    # 生成截止到 END_DATE 的最近 N_BARS 个交易日
    all_days = trading_days(date(2022, 1, 1), END_DATE)
    days = all_days[-N_BARS:]

    rng = np.random.default_rng(SEED)
    count = 0
    for code, profile in _SYMBOLS:
        market = resolve_market_dir(code)
        lday = demo_root / market / "lday"
        lday.mkdir(parents=True, exist_ok=True)
        path = lday / f"{market}{code}.day"
        rows = _gen_symbol(code, profile, days, rng)
        _write_day_file(path, rows)
        count += 1

    print(f"✅ 已生成 {count} 只演示标的（每只 {len(days)} 根日线）→ {demo_root}")
    return days


def generate_snapshot(demo_root: Path) -> None:
    """用演示数据跑回测引擎，生成概览页快照（复用 make_dashboard_snapshot）。"""
    # 让 make_dashboard_snapshot 的加载函数读到演示数据目录
    os.environ["STOCK_HSJDAY_ROOT"] = str(demo_root)
    sys.path.insert(0, str(ROOT / "scripts"))

    from make_dashboard_snapshot import build_snapshot, load_universe
    from strategies import REGISTRY

    end = END_DATE
    # 最近约 60 个交易日：选择性/超额胜率/基线都有统计意义，且回测很快
    start = trading_days(end - timedelta(days=180), end)[-60]
    candles, kind_map = load_universe(end)

    symbols_by_strategy: dict[str, set[str]] = {}
    for strategy, mod in REGISTRY.items():
        allowed = set(mod.TARGET_KINDS)
        symbols_by_strategy[strategy] = {
            s for s in candles if kind_map.get(s) in allowed
        }

    snapshot = build_snapshot(start, end, 1, candles, kind_map, symbols_by_strategy)
    snapshot["last_scan"]["duration_seconds"] = 0.1
    snapshot["last_scan"]["symbols_scanned"] = len(candles)

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"✅ 已生成概览页快照 → {SNAPSHOT_PATH}")


def main() -> None:
    days = generate_demo_data(DEMO_ROOT)
    _ = days
    generate_snapshot(DEMO_ROOT)

    print()
    print("下一步（启动 API 读演示数据）：")
    print(f"  STOCK_HSJDAY_ROOT=\"{DEMO_ROOT}\" .venv/bin/uvicorn main:app \\")
    print(f"      --app-dir apps/api/src --port 8000")
    print("  前端：cd apps/web && npm run dev，浏览器打开 http://localhost:3000")


if __name__ == "__main__":
    main()
