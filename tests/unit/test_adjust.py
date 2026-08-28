"""复权处理（market.adjust）单元测试：除权检测 + 前/后复权换算。"""

from __future__ import annotations

import numpy as np
import pytest

from market.adjust import (
    DEFAULT_ADJUST_MODE,
    AdjustMode,
    backward_adjust_closes,
    detect_ex_rights,
    forward_adjust_closes,
    forward_adjust_frame,
    limit_down_pct,
)
from tests.helpers import make_candle_df


def test_adjust_mode_default_is_forward():
    assert DEFAULT_ADJUST_MODE is AdjustMode.FORWARD


def test_limit_down_by_board():
    assert limit_down_pct("600519") == pytest.approx(-0.105)
    assert limit_down_pct("000001") == pytest.approx(-0.105)
    assert limit_down_pct("300750") == pytest.approx(-0.205)
    assert limit_down_pct("688981") == pytest.approx(-0.205)
    # 未知归主板
    assert limit_down_pct("999999") == pytest.approx(-0.105)


def test_detect_ex_rights_flags_large_gap_only():
    # 10 → 5（-50%，除权）应判为除权；10 → 9.5（-5%，普通下跌）不应判
    closes = [10.0, 9.5, 5.0, 5.1]
    ex = detect_ex_rights(closes, -0.105)
    assert ex.tolist() == [False, False, True, False]


def test_forward_adjust_removes_ex_rights_gap():
    # 10 → 5（1:1 拆股），之后 5 → 5.5（+10%）。前复权后历史价格折半，除权日收益≈0。
    closes = [10.0, 5.0, 5.5]
    ex = detect_ex_rights(closes, -0.105)
    adj = forward_adjust_closes(closes, ex)

    # 最新价不变
    assert adj[-1] == pytest.approx(5.5)
    # 除权日（index 1）复权收益 ≈ 0
    assert adj[1] / adj[0] - 1.0 == pytest.approx(0.0, abs=1e-9)
    # 后续收益保持真实：5.5 / 5 = +10%
    assert adj[2] / adj[1] - 1.0 == pytest.approx(0.10)


def test_forward_adjust_frame_scales_ohlc_only():
    closes = [10.0, 5.0, 5.5]
    df = make_candle_df(closes, volume=1000.0)
    adj = forward_adjust_frame(df, "600000")

    # close 前复权后与 forward_adjust_closes 一致
    expected = forward_adjust_closes(np.asarray(closes, dtype=float), detect_ex_rights(closes, -0.105))
    assert adj["close"].tolist() == pytest.approx(expected.tolist())
    # 成交量 / 成交额不变
    assert adj["volume"].tolist() == df["volume"].tolist()
    assert adj["amount"].tolist() == df["amount"].tolist()
    # 最新价不变（前复权以最新价为锚）
    assert adj["close"].iloc[-1] == pytest.approx(5.5)


def test_backward_adjust_scales_latest_price():
    closes = [10.0, 5.0, 5.5]
    ex = detect_ex_rights(closes, -0.105)
    adj = backward_adjust_closes(closes, ex)
    # 后复权：最早价不变，最新价被缩放（累计收益 = 总回报）
    assert adj[0] == pytest.approx(10.0)
    # 除权日（index 1）后复权收益 ≈ 0（因子向后传递）
    assert adj[1] / adj[0] - 1.0 == pytest.approx(0.0, abs=1e-9)


def test_no_ex_rights_leaves_prices_unchanged():
    closes = [10.0, 10.5, 10.2, 11.0]
    ex = detect_ex_rights(closes, -0.105)
    assert not ex.any()
    assert forward_adjust_closes(closes, ex).tolist() == pytest.approx(closes)
