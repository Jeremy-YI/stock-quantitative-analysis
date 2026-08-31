"""回测评级机械判定（scripts/build_strategy_ratings.py 的 classify）。

产品红线：只有回测过关的战法能进客户推荐，判定必须机械、可复现，
不能靠 Obsidian 笔记或人工印象。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from build_strategy_ratings import classify  # noqa: E402


def _w(excess: float, n: int = 5000, selectivity: float = 0.1) -> dict:
    return {"excess_win_rate": excess, "n": n, "selectivity": selectivity}


def test_all_positive_is_robust():
    rating, _ = classify(
        {"IS": _w(0.05), "OOS-A": _w(0.03), "OOS-B": _w(0.02), "OOS-C": _w(0.04)}
    )
    assert rating == "robust"


def test_oos_all_positive_with_negative_is_is_oos_positive():
    # pin30：样本内负、样本外三段全正
    rating, _ = classify(
        {"IS": _w(-0.02), "OOS-A": _w(0.021), "OOS-B": _w(0.008), "OOS-C": _w(0.012)}
    )
    assert rating == "oos_positive"


def test_mixed_is_regime():
    # double_bottom：四段有正有负
    rating, _ = classify(
        {"IS": _w(-0.073), "OOS-A": _w(-0.026), "OOS-B": _w(0.074), "OOS-C": _w(-0.039)}
    )
    assert rating == "regime"


def test_is_positive_oos_all_negative_is_overfit():
    rating, _ = classify(
        {"IS": _w(0.05), "OOS-A": _w(-0.01), "OOS-B": _w(-0.02), "OOS-C": _w(-0.03)}
    )
    assert rating == "overfit"


def test_thin_samples_is_insufficient():
    # etf_accumulation：OOS-A n=64、OOS-C n=24，低于红线
    rating, reason = classify(
        {
            "IS": _w(0.315, 5000),
            "OOS-A": _w(-0.195, 64),
            "OOS-B": _w(0.428, 442),
            "OOS-C": _w(0.218, 24),
        }
    )
    assert rating == "insufficient"
    assert "样本量不足" in reason


def test_high_selectivity_is_no_edge():
    # b1b2b3：选择性 63%，每天推半个市场
    rating, reason = classify(
        {"IS": _w(-0.005, 5000, 0.63), "OOS-A": _w(0.002, 5000, 0.63)}
    )
    assert rating == "no_edge"
    assert "选择性" in reason


def test_flat_is_no_edge():
    rating, _ = classify({"IS": _w(0.004), "OOS-A": _w(-0.003), "OOS-B": _w(0.006)})
    assert rating == "no_edge"
