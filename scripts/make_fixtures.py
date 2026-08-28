"""生成测试 fixtures（真实标的切片 + MACD 黄金值）。

数据源：本地通达信 hsjday（~/Desktop/每日复盘/hsjday）。
产物：
    tests/fixtures/600519_daily.csv          日线切片（最近 WINDOW_BARS 根）
    tests/fixtures/600519_macd_golden.csv   对应的 MACD 黄金值（dif/dea/macd）

黄金值 = 用当前 indicators.macd.calc_macd 在切片 close 上跑一遍的结果，
作为回归基准提交进仓库；测试用同一算法算一遍再逐点比对（精确到 4 位小数），
一旦有人改动 EMA 种子 / 周期 / 柱倍数，测试就会失败。

运行（仓库根目录）：
    .venv/bin/python scripts/make_fixtures.py
"""

from __future__ import annotations

import csv
from pathlib import Path

from datasource.tdx import parse_day_file, resolve_symbol_path
from indicators.macd import calc_macd

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

    print(f"✅ 已生成 {daily_path}（{len(df)} 根 K 线）")
    print(f"✅ 已生成 {golden_path}")
    print(f"   日期区间：{df['date'].iloc[0].isoformat()} ~ {df['date'].iloc[-1].isoformat()}")


if __name__ == "__main__":
    main()
