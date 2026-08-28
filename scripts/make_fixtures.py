"""生成测试 fixtures（真实标的切片 + MACD/KDJ/RSI/量能黄金值）。

数据源：本地通达信 hsjday（~/Desktop/每日复盘/hsjday）。
产物：
    tests/fixtures/600519_daily.csv           日线切片（最近 WINDOW_BARS 根）
    tests/fixtures/600519_macd_golden.csv    MACD 黄金值（dif/dea/macd）
    tests/fixtures/600519_kdj_golden.csv     KDJ 黄金值（k/d/j）
    tests/fixtures/600519_rsi_golden.csv     RSI 黄金值（rsi）
    tests/fixtures/600519_volume_golden.csv  量能黄金值（mavol1/mavol2/volume_ratio/relation）

黄金值 = 用当前 indicators 各模块在切片上跑一遍的结果，作为回归基准提交进仓库；
测试用同一算法算一遍再逐点比对，一旦有人改动公式（种子/周期/平滑权重），
测试就会失败。

运行（仓库根目录）：
    .venv/bin/python scripts/make_fixtures.py
"""

from __future__ import annotations

import csv
from pathlib import Path

from datasource.tdx import parse_day_file, resolve_hsjday_root, resolve_symbol_path
from indicators.kdj import calc_kdj
from indicators.macd import calc_macd
from indicators.rsi import calc_rsi
from indicators.volume import (
    calc_volume_ma,
    calc_volume_ratio,
    classify_price_volume,
)

ROOT = Path(__file__).resolve().parent.parent
# 数据根目录：优先读环境变量 STOCK_HSJDAY_ROOT，缺省用本地默认路径
HSJDAY = resolve_hsjday_root()
FIXTURES_DIR = ROOT / "tests" / "fixtures"

SYMBOL = "600519"
WINDOW_BARS = 40  # 切多少根 K 线做黄金值基准

# 全市场抽样 fixture：覆盖不同板块/前缀的代表标的（确保一致性测试有真实形态）
MARKET_CURATED = [
    "600519", "600036", "600028", "601318", "603288", "605499",  # 沪主板
    "688981", "688111",  # 科创板
    "000001", "000002", "000858", "002415", "002594", "003816",  # 深主板/中小
    "300750", "300059", "301236",  # 创业板
    # 下面这批是 2026-08-27 真实触发 macd_resonance 的代表，保证快照非空
    "000008", "000017", "000045", "000407", "000426", "000428",
    "000506", "000520", "001225", "002004", "003003", "300012",
]
MARKET_TARGET = 80  # 抽样总只数（含 curated）
MARKET_WINDOW_BARS = 900  # 每只切最近多少根日线（macd 月线需 30 月 ≈ 660 日，留余量）


def main() -> None:
    path = resolve_symbol_path(HSJDAY, SYMBOL)
    df = parse_day_file(path).tail(WINDOW_BARS).reset_index(drop=True)

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    # 1) 日线切片
    daily_path = FIXTURES_DIR / f"{SYMBOL}_daily.csv"
    with daily_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "open", "high", "low", "close", "volume", "amount"])
        for row in df.to_dict("records"):
            writer.writerow(
                [
                    row["date"].isoformat(),
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                    row["amount"],
                ]
            )

    # 2) MACD 黄金值
    closes = df["close"].tolist()
    result = calc_macd(closes)
    golden_path = FIXTURES_DIR / f"{SYMBOL}_macd_golden.csv"
    with golden_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["dif", "dea", "macd"])
        for i in range(len(closes)):
            writer.writerow(
                [
                    round(result.dif[i], 6),
                    round(result.dea[i], 6),
                    round(result.macd[i], 6),
                ]
            )

    # 3) KDJ 黄金值
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    kdj = calc_kdj(highs, lows, closes)
    kdj_path = FIXTURES_DIR / f"{SYMBOL}_kdj_golden.csv"
    with kdj_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["k", "d", "j"])
        for i in range(len(closes)):
            writer.writerow([
                round(kdj.k[i], 6),
                round(kdj.d[i], 6),
                round(kdj.j[i], 6),
            ])

    # 4) RSI 黄金值
    rsi = calc_rsi(closes)
    rsi_path = FIXTURES_DIR / f"{SYMBOL}_rsi_golden.csv"
    with rsi_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["rsi"])
        for i in range(len(closes)):
            writer.writerow([round(rsi[i], 6)])

    # 5) 量能黄金值
    volumes = df["volume"].tolist()
    vol_ma = calc_volume_ma(volumes)
    vol_ratio = calc_volume_ratio(volumes)
    relations = classify_price_volume(closes, volumes)
    volume_path = FIXTURES_DIR / f"{SYMBOL}_volume_golden.csv"
    with volume_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["mavol1", "mavol2", "volume_ratio", "relation"])
        for i in range(len(closes)):
            writer.writerow([
                round(vol_ma.mavol1[i], 6),
                round(vol_ma.mavol2[i], 6),
                round(vol_ratio[i], 6),
                relations[i],
            ])

    print(f"✅ 已生成 {daily_path}（{len(df)} 根 K 线）")
    print(f"✅ 已生成 {golden_path}")
    print(f"✅ 已生成 {kdj_path}")
    print(f"✅ 已生成 {rsi_path}")
    print(f"✅ 已生成 {volume_path}")
    print(f"   日期区间：{df['date'].iloc[0].isoformat()} ~ {df['date'].iloc[-1].isoformat()}")

    make_market_fixture()


def make_market_fixture() -> None:
    """生成全市场抽样 fixture：tests/fixtures/market_daily.csv。

    从本地 hsjday 按确定性规则抽样 ``MARKET_TARGET`` 只 A股个股（覆盖沪/深/
    主板/科创/创业板），每只切最近 ``MARKET_WINDOW_BARS`` 根日线，合并写入
    单个 CSV（含 symbol 列）。供策略层一致性测试使用。
    """
    from strategies.filters import SymbolKind, classify_symbol

    market_csv = FIXTURES_DIR / "market_daily.csv"

    # 收集全部个股代码（按市场 + 前缀去重、排序，确定性）
    codes: list[tuple[str, str]] = []
    for market in ("sh", "sz", "bj"):
        lday = HSJDAY / market / "lday"
        if not lday.is_dir():
            continue
        for fn in sorted(lday.iterdir()):
            if not fn.name.endswith(".day"):
                continue
            code = fn.name[2:8]
            if len(code) != 6:
                continue
            if classify_symbol(market, code) is SymbolKind.STOCK:
                codes.append((market, code))

    # curated 优先，再等间隔抽到 MARKET_TARGET 只
    curated = [(resolve_market(c), c) for c in MARKET_CURATED]
    selected: list[tuple[str, str]] = list(curated)
    rest = [mc for mc in codes if mc not in selected]
    if rest:
        step = max(1, len(rest) // max(1, MARKET_TARGET - len(selected)))
        for i in range(0, len(rest), step):
            selected.append(rest[i])
            if len(selected) >= MARKET_TARGET:
                break

    rows: list[dict] = []
    for market, code in selected:
        path = HSJDAY / market / "lday" / f"{market}{code}.day"
        if not path.exists():
            continue
        df = parse_day_file(path).tail(MARKET_WINDOW_BARS).reset_index(drop=True)
        for row in df.to_dict("records"):
            rows.append({"symbol": code, **row})

    with market_csv.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["symbol", "date", "open", "high", "low", "close", "volume", "amount"]
        )
        writer.writeheader()
        for r in rows:
            writer.writerow({**r, "date": r["date"].isoformat()})

    n_symbols = len({r["symbol"] for r in rows})
    print(f"✅ 已生成 {market_csv}（{n_symbols} 只 / {len(rows)} 行）")


def resolve_market(code: str) -> str:
    """按代码前缀判定市场（与 datasource.resolve_market 一致）。"""
    from datasource.tdx import resolve_market as _resolve_market

    return _resolve_market(code)


if __name__ == "__main__":
    main()
