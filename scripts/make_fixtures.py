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

from datasource.tdx import parse_day_file, resolve_symbol_path
from indicators.kdj import calc_kdj
from indicators.macd import calc_macd
from indicators.rsi import calc_rsi
from indicators.volume import (
    calc_volume_ma,
    calc_volume_ratio,
    classify_price_volume,
)

ROOT = Path(__file__).resolve().parent.parent
HSJDAY = Path.home() / "Desktop" / "每日复盘" / "hsjday"
FIXTURES_DIR = ROOT / "tests" / "fixtures"

SYMBOL = "600519"
WINDOW_BARS = 40  # 切多少根 K 线做黄金值基准


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


if __name__ == "__main__":
    main()
