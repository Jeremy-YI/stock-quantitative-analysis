"""阶段 14 第一步（门禁）：159828 医疗ETF 案例回归测试——MACD 柱状阶段顶底 + 2 日容错 + 洗盘判别。

把 Jeremy 的架构复现成断言（数据源 = 本地通达信 hsjday，文件不存在则 skip）：

- **阶段性底部** 3/23-3/26：绿柱 3/24 最深(-0.050) → 3/25(-0.040) → 3/26(-0.038) 收缩
  → 柱状底部确认日 = 3/25（收缩第一天）。
- **阶段性顶部** 7/06：红柱 7/03 最高(+0.082) → 7/06(+0.082) 收缩，叠加长上影 61.5%。
- **7/29 绿柱底背离买点**：绿柱 7/28(-0.003) → 7/29(-0.001) 收缩 → 柱状底部确认日 = 7/29。
- **8/24 单针 + 未破 4.21 = 洗盘**：单针(短 7.1)触发，进攻 K 防线 4.21，收盘 4.21 未破。

复现口径（不得自己改 Jeremy 口径去凑）：
- 柱状极值用已收盘 bar 判定，确认日 = 收缩第一天，尾盘买用收盘价。
- 破位容错：连续 2 个交易日收盘跌破才算破，单日破不算。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from datasource.tdx import parse_day_file, resolve_hsjday_root, resolve_symbol_path
from indicators.macd import calc_macd
from indicators.stage13 import attack_midpoint, upper_shadow_ratio
from indicators.stage14 import (
    attack_defense_series,
    detect_hist_stage_bottoms,
    detect_hist_stage_tops,
    lifeline_series,
    line_broken_2day,
)


@pytest.fixture(scope="module")
def df_159828() -> pd.DataFrame:
    root = resolve_hsjday_root()
    path = resolve_symbol_path(root, "159828")
    if not Path(path).exists():
        pytest.skip("本地 hsjday 无 159828 数据，跳过")
    return parse_day_file(path)


@pytest.fixture(scope="module")
def hist_159828(df_159828: pd.DataFrame) -> np.ndarray:
    closes = df_159828["close"].astype(float).tolist()
    _, _, hist = calc_macd(closes)
    return np.asarray(hist, dtype=float)


def _date_index(df: pd.DataFrame) -> dict[date, int]:
    return {d: i for i, d in enumerate(df["date"].to_numpy())}


def _idx(df: pd.DataFrame, s: str) -> int:
    return _date_index(df)[date.fromisoformat(s)]


def test_stage_bottom_325(df_159828: pd.DataFrame, hist_159828: np.ndarray) -> None:
    """阶段性底部 3/25：绿柱 3/24 最深(-0.050)后 3/25(-0.040) 收缩。"""
    i25 = _idx(df_159828, "2026-03-25")
    i24 = _idx(df_159828, "2026-03-24")
    i26 = _idx(df_159828, "2026-03-26")
    # 3/24 最深，之后连续收缩
    assert float(hist_159828[i24]) == pytest.approx(-0.0495, abs=5e-3)
    assert float(hist_159828[i25]) > float(hist_159828[i24])
    assert float(hist_159828[i26]) > float(hist_159828[i25])
    for n in (5, 10):
        assert i25 in detect_hist_stage_bottoms(hist_159828.tolist(), n), f"N={n} 应命中 3/25"


def test_stage_bottom_729(df_159828: pd.DataFrame, hist_159828: np.ndarray) -> None:
    """7/29 绿柱底背离买点：绿柱 7/28(-0.003) → 7/29(-0.001) 收缩。"""
    i28 = _idx(df_159828, "2026-07-28")
    i29 = _idx(df_159828, "2026-07-29")
    assert float(hist_159828[i28]) < 0.0
    assert float(hist_159828[i29]) > float(hist_159828[i28])
    assert float(hist_159828[i29]) == pytest.approx(-0.0007, abs=5e-3)
    for n in (5, 10, 20):
        assert i29 in detect_hist_stage_bottoms(hist_159828.tolist(), n), f"N={n} 应命中 7/29"


def test_stage_top_706(df_159828: pd.DataFrame, hist_159828: np.ndarray) -> None:
    """阶段性顶部 7/06：红柱 7/03 最高(+0.082)后 7/06(+0.082) 收缩。"""
    i03 = _idx(df_159828, "2026-07-03")
    i06 = _idx(df_159828, "2026-07-06")
    assert float(hist_159828[i03]) > 0.0
    assert float(hist_159828[i06]) < float(hist_159828[i03])
    assert float(hist_159828[i06]) > 0.0
    for n in (5, 10, 20):
        assert i06 in detect_hist_stage_tops(hist_159828.tolist(), n), f"N={n} 应命中 7/06"


def test_stage_top_706_upper_shadow(df_159828: pd.DataFrame) -> None:
    """7/06 阶段性顶部叠加长上影 61.5%（防守印证）。"""
    i = _idx(df_159828, "2026-07-06")
    o = float(df_159828["open"].iloc[i])
    h = float(df_159828["high"].iloc[i])
    l = float(df_159828["low"].iloc[i])
    c = float(df_159828["close"].iloc[i])
    ratio = upper_shadow_ratio(o, h, l, c)
    assert ratio == pytest.approx(0.6154, abs=1e-3)


def test_stage_bottom_n20_misses_325(df_159828: pd.DataFrame, hist_159828: np.ndarray) -> None:
    """N=20 太慢，3/25 阶段性底部被吞（记录在案，不是 bug）。"""
    i25 = _idx(df_159828, "2026-03-25")
    assert i25 not in detect_hist_stage_bottoms(hist_159828.tolist(), 20)


def test_lifeline_series_reproduces_3880(df_159828: pd.DataFrame) -> None:
    """生命线序列在 7/07 处 = 3.880（5/21 高4.17 + 6/09 低3.59）/2。"""
    highs = df_159828["high"].astype(float).tolist()
    lows = df_159828["low"].astype(float).tolist()
    closes = df_159828["close"].astype(float).tolist()
    ll = lifeline_series(highs, lows, closes, k=3)
    i707 = _idx(df_159828, "2026-07-07")
    assert ll[i707] == pytest.approx(3.880, abs=1e-9)


def test_2day_tolerance_707(df_159828: pd.DataFrame) -> None:
    """破位容错：7/07 收盘 3.81 破生命线 3.88 但仅 1 日 → 不算破；7/08 连续 2 日 → 算破。"""
    closes = df_159828["close"].astype(float).tolist()
    i706 = _idx(df_159828, "2026-07-06")
    i707 = _idx(df_159828, "2026-07-07")
    i708 = _idx(df_159828, "2026-07-08")
    lifeline = 3.880
    assert float(closes[i707]) < lifeline          # 7/07 单日破
    assert float(closes[i706]) >= lifeline         # 前日未破
    assert line_broken_2day(closes, lifeline, i707) is False  # 单日破不算（洗盘容错）
    assert float(closes[i708]) < lifeline          # 7/08 连续第 2 日
    assert line_broken_2day(closes, lifeline, i708) is True   # 连续 2 日才算破


def test_washout_824_attack_not_broken(df_159828: pd.DataFrame) -> None:
    """8/24 单针 + 进攻 K 防线 4.21 未破（收盘 4.21 == 4.21）→ 判为洗盘。"""
    opens = df_159828["open"].astype(float).tolist()
    highs = df_159828["high"].astype(float).tolist()
    lows = df_159828["low"].astype(float).tolist()
    closes = df_159828["close"].astype(float).tolist()
    i824 = _idx(df_159828, "2026-08-24")
    # 单针：短期随机 ≤ 30（复用 stage13 口径）
    lv = pd.Series(lows).rolling(3, min_periods=1).min().to_numpy(dtype=float)
    hv = pd.Series(closes).rolling(3, min_periods=1).max().to_numpy(dtype=float)
    den = hv - lv
    short = np.where(den <= 0, 50.0, (closes - lv) / (den + 0.0001) * 100.0)
    assert float(short[i824]) <= 30.0
    # 进攻 K 防线 = 4.21（8/07 进攻 K 中点）
    ad = attack_defense_series(opens, highs, lows, closes, "etf")
    assert ad[i824] == pytest.approx(4.210, abs=1e-9)
    assert float(closes[i824]) == pytest.approx(4.210, abs=1e-9)
    # 2 日容错：收盘 4.21 未破 4.21 → 不破 → 洗盘
    assert line_broken_2day(closes, ad[i824], i824) is False
    # 进攻 K 中点公式正确性（8/07）
    i807 = _idx(df_159828, "2026-08-07")
    assert attack_midpoint(float(opens[i807]), float(closes[i807])) == pytest.approx(4.210, abs=1e-9)
