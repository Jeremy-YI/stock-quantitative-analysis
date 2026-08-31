"""阶段 13 第一步：159828 医疗ETF 案例回归测试。

把 Jeremy 在 2026-02~2026-08 手工标注的全部点位复现成断言。数据源 = 本地通达信
hsjday（``resolve_hsjday_root``），文件不存在则跳过（同 integration 测试口径）。

复现口径（不得自己改 Jeremy 口径去凑）：
- 生命线1 = 0.4055（3/17 高 0.427 + 3/23 低 0.384）/2
- 生命线2 = 0.3880（5/21 高 0.417 + 6/09 低 0.359）/2
- 进攻 K 中点（6/29）= 0.3775、（8/07）= 0.4210 —— (开盘+收盘)/2
- 7/06 长上影线（上影占全长 62%）
- 7/07 跌破生命线、7/10 站回（洗盘）
- 8/24 单针触发（短期 7.1、长期 49.0）且未破 0.421

注：2026-08-31 修正通达信基金价格比例（ETF 是 ×1000 不是 ×100）后，
本文件的价格锚点整体 ÷10（159828 医疗ETF 真实价 ~0.42，之前读成 ~4.2）。
形态关系（生命线=(高+低)/2、进攻K中点、破位容错）不受影响，只是小数点位置。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from datasource.tdx import parse_day_file, resolve_hsjday_root, resolve_symbol_path
from indicators.divergence import swing_highs, swing_lows
from indicators.macd import calc_macd
from indicators.stage13 import (
    attack_midpoint,
    detect_attack_candles,
    detect_bottom_divergences,
    is_long_upper_shadow,
    lifeline_value,
    upper_shadow_ratio,
)


@pytest.fixture(scope="module")
def df_159828() -> pd.DataFrame:
    root = resolve_hsjday_root()
    path = resolve_symbol_path(root, "159828")
    if not Path(path).exists():
        pytest.skip("本地 hsjday 无 159828 数据，跳过")
    return parse_day_file(path)


def _date_index(df: pd.DataFrame) -> dict[date, int]:
    return {d: i for i, d in enumerate(df["date"].to_numpy())}


def _idx(df: pd.DataFrame, s: str) -> int:
    return _date_index(df)[date.fromisoformat(s)]


def test_lifeline1(df_159828: pd.DataFrame) -> None:
    """生命线1 = 0.4055（3/17 高 0.427 + 3/23 低 0.384）。"""
    df = df_159828
    highs = df["high"].astype(float).to_numpy()
    lows = df["low"].astype(float).to_numpy()
    closes = df["close"].astype(float).to_numpy()

    i_top = _idx(df, "2026-03-17")
    i_bot = _idx(df, "2026-03-23")
    assert highs[i_top] == pytest.approx(0.427, abs=1e-9)
    assert lows[i_bot] == pytest.approx(0.384, abs=1e-9)
    assert lifeline_value(highs[i_top], lows[i_bot]) == pytest.approx(0.4055, abs=1e-9)


def test_lifeline2(df_159828: pd.DataFrame) -> None:
    """生命线2 = 0.3880（5/21 高 0.417 + 6/09 低 0.359）。"""
    df = df_159828
    highs = df["high"].astype(float).to_numpy()
    lows = df["low"].astype(float).to_numpy()

    i_top = _idx(df, "2026-05-21")
    i_bot = _idx(df, "2026-06-09")
    assert highs[i_top] == pytest.approx(0.417, abs=1e-9)
    assert lows[i_bot] == pytest.approx(0.359, abs=1e-9)
    assert lifeline_value(highs[i_top], lows[i_bot]) == pytest.approx(0.3880, abs=1e-9)


def test_k3_pivots_match_anchors(df_159828: pd.DataFrame) -> None:
    """k=3 区间化摆动点能同时命中 4 个锚点（3/17、3/23、5/21、6/09）。"""
    df = df_159828
    highs = df["high"].astype(float).tolist()
    lows = df["low"].astype(float).tolist()

    sh = set(swing_highs(highs, 3))
    sl = set(swing_lows(lows, 3))
    for s in ("2026-03-17", "2026-05-21"):
        assert _idx(df, s) in sh, f"k=3 摆动高点缺失 {s}"
    for s in ("2026-03-23", "2026-06-09"):
        assert _idx(df, s) in sl, f"k=3 摆动低点缺失 {s}"


def test_bottom_divergences_reproduce_lifelines(df_159828: pd.DataFrame) -> None:
    """底背离（收盘创新低 + 区间顶）能算出生命线 0.4055 / 0.3880。"""
    df = df_159828
    highs = df["high"].astype(float).tolist()
    lows = df["low"].astype(float).tolist()
    closes = df["close"].astype(float).tolist()

    events = detect_bottom_divergences(lows, closes, highs, k=3)
    got: dict[int, float] = {}
    for e in events:
        if e.is_new_low and e.top_idx >= 0:
            got[e.idx] = lifeline_value(e.top_high, e.low)

    i_bot1 = _idx(df, "2026-03-23")
    i_bot2 = _idx(df, "2026-06-09")
    assert i_bot1 in got and got[i_bot1] == pytest.approx(0.4055, abs=1e-9)
    assert i_bot2 in got and got[i_bot2] == pytest.approx(0.3880, abs=1e-9)


def test_attack_midpoint_629(df_159828: pd.DataFrame) -> None:
    """进攻 K 中点 6/29 = 0.3775（(开盘+收盘)/2，不是 (高+低)/2=0.375）。"""
    df = df_159828
    i = _idx(df, "2026-06-29")
    o = float(df["open"].iloc[i])
    c = float(df["close"].iloc[i])
    assert attack_midpoint(o, c) == pytest.approx(0.3775, abs=1e-9)
    # (高+低)/2 = 0.375，与 Jeremy 用的 0.3775 不同
    h = float(df["high"].iloc[i])
    l = float(df["low"].iloc[i])
    assert (h + l) / 2 == pytest.approx(0.375, abs=1e-9)


def test_attack_midpoint_807(df_159828: pd.DataFrame) -> None:
    """进攻 K 中点 8/07 = 0.4210。"""
    df = df_159828
    i = _idx(df, "2026-08-07")
    o = float(df["open"].iloc[i])
    c = float(df["close"].iloc[i])
    assert attack_midpoint(o, c) == pytest.approx(0.4210, abs=1e-9)


def test_attack_candles_detected(df_159828: pd.DataFrame) -> None:
    """ETF ≥4% 涨幅的进攻 K 应命中 6/29、7/15、8/07、8/20 四根。"""
    df = df_159828
    opens = df["open"].astype(float).tolist()
    closes = df["close"].astype(float).tolist()
    idx = detect_attack_candles(opens, closes, symbol="etf")
    got = {i for i in idx}
    for s in ("2026-06-29", "2026-07-15", "2026-08-07", "2026-08-20"):
        assert _idx(df, s) in got, f"进攻 K 缺失 {s}"


def test_attack_stack_824_not_broken(df_159828: pd.DataFrame) -> None:
    """栈逻辑：8/24 当前有效进攻 K 中点 = 8/07 的 0.421，收盘 0.421 未破。"""
    df = df_159828
    opens = df["open"].astype(float).tolist()
    closes = df["close"].astype(float).tolist()
    mids = [attack_midpoint(o, c) for o, c in zip(opens, closes)]
    atk = detect_attack_candles(opens, closes, symbol="etf")

    from indicators.stage13 import current_attack_midpoint

    i824 = _idx(df, "2026-08-24")
    cur = current_attack_midpoint(atk, closes, mids, i824)
    assert cur == pytest.approx(0.4210, abs=1e-9)
    # 收盘 0.421 == 中点 0.421，不算破（破用收盘价、严格 < ）
    assert float(df["close"].iloc[i824]) == pytest.approx(0.421, abs=1e-9)
    assert not (float(df["close"].iloc[i824]) < cur)


def test_upper_shadow_706(df_159828: pd.DataFrame) -> None:
    """7/06 长上影线：开 3.93 高 4.02 低 3.89 收 0.394，上影占全长 61.5%。"""
    df = df_159828
    i = _idx(df, "2026-07-06")
    o = float(df["open"].iloc[i])
    h = float(df["high"].iloc[i])
    l = float(df["low"].iloc[i])
    c = float(df["close"].iloc[i])
    ratio = upper_shadow_ratio(o, h, l, c)
    assert ratio == pytest.approx(0.6154, abs=1e-3)
    # 60% 阈值判定为真；70% 阈值判定为假
    assert is_long_upper_shadow(o, h, l, c, 0.6) is True
    assert is_long_upper_shadow(o, h, l, c, 0.7) is False


def test_lifeline_break_and_recover(df_159828: pd.DataFrame) -> None:
    """7/07 收盘 0.381 破生命线 0.388，7/10 收盘 0.394 站回（洗盘）。"""
    df = df_159828
    closes = df["close"].astype(float).to_numpy()
    i707 = _idx(df, "2026-07-07")
    i710 = _idx(df, "2026-07-10")
    lifeline = 0.3880
    assert float(closes[i707]) < lifeline
    assert float(closes[i710]) > lifeline


def test_pin_824(df_159828: pd.DataFrame) -> None:
    """8/24 单针触发：短期随机 7.1、长期 49.0，且未破 0.421。"""
    df = df_159828
    closes = df["close"].astype(float).to_numpy()
    lows = df["low"].astype(float).to_numpy()

    def stoch(lookback: int) -> np.ndarray:
        lv = pd.Series(lows).rolling(lookback, min_periods=1).min().to_numpy(dtype=float)
        hv = pd.Series(closes).rolling(lookback, min_periods=1).max().to_numpy(dtype=float)
        den = hv - lv
        return np.where(den <= 0, 50.0, (closes - lv) / (den + 0.0001) * 100.0)

    i824 = _idx(df, "2026-08-24")
    short = stoch(3)
    long_ = stoch(20)
    assert float(short[i824]) == pytest.approx(7.14, abs=0.05)
    assert float(long_[i824]) == pytest.approx(49.0, abs=0.1)
    assert float(short[i824]) <= 30.0
    assert float(closes[i824]) >= 0.421 - 1e-9  # 未破 0.421


def test_macd_hist_increment_capital(df_159828: pd.DataFrame) -> None:
    """增量资金：3/23~3/26 绿柱 3/24 最深(-0.0050)后连续收缩，价格仍跌。"""
    df = df_159828
    closes = df["close"].astype(float).tolist()
    _, _, hist = calc_macd(closes)
    i23 = _idx(df, "2026-03-23")
    i24 = _idx(df, "2026-03-24")
    i25 = _idx(df, "2026-03-25")
    i26 = _idx(df, "2026-03-26")
    assert float(hist[i24]) == pytest.approx(-0.00495, abs=5e-4)
    # 3/24 最深，之后连续收缩（变浅）
    assert float(hist[i24]) <= float(hist[i23])
    assert float(hist[i25]) > float(hist[i24])
    assert float(hist[i26]) > float(hist[i25])
