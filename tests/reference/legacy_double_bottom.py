"""旧脚本参考实现：美股双底(W底)扫描核心逻辑（仅用于一致性测试）。

从 `~/.openclaw/workspace/tools/us_double_bottom.py::detect_double_bottom`
原样抽取（去掉 yfinance 拉取与输出，只留纯形态判定），参数默认值与旧脚本
顶部常量一致。请勿在业务代码 import 本模块。

与新实现的差异（一致性测试只比对「形态判定」部分，其余差异见
docs/双底反弹迁移说明.md）：

    - 流动性：旧脚本用 ``closes × volume`` 近似「美元成交额」；新实现用 A股
      hsjday 的 ``amount``（成交额，元）列。一致性测试把两边的流动性门槛都
      关掉（min_dollar_vol=0 / min_amount=0）后比对标的选择集合。
    - 回撤基准：旧脚本 ``max(highs)`` 取全窗口；新实现取近 drawdown_window。
      回撤只影响 score 不影响选择，故一致性比对不受影响。
"""

from __future__ import annotations

from typing import Sequence

# 旧脚本顶部常量（默认参数原样保留）
SWING_K = 6
RECENT = 12
MIN_GAP = 12
MAX_GAP = 90
TOL_HIGHER = 0.03
TOL_LOWER = 0.03
MIN_RALLY = 0.12
L2_LOW_ZONE = 1.05
MAX_ABOVE_NECK = 0.15
MIN_PRICE = 5.0
MIN_DOLLAR_VOL = 2e7
MIN_BARS = 150


def _ema(d: Sequence[float], p: int) -> list[float]:
    k = 2.0 / (p + 1)
    r = [d[0]]
    for i in range(1, len(d)):
        r.append(d[i] * k + r[-1] * (1 - k))
    return r


def _macd(closes: Sequence[float], fast=12, slow=26, sig=9):
    ef, es = _ema(closes, fast), _ema(closes, slow)
    dif = [ef[i] - es[i] for i in range(len(closes))]
    dea = _ema(dif, sig)
    hist = [(dif[i] - dea[i]) * 2 for i in range(len(closes))]
    return dif, dea, hist


def _rsi_series(closes: Sequence[float], period=14) -> list[float]:
    n = len(closes)
    out = [50.0] * n
    if n < period + 1:
        return out
    gains, losses = [], []
    for i in range(1, n):
        ch = closes[i] - closes[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    out[period] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
        out[i + 1] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def _swing_lows(lows: Sequence[float], k=SWING_K) -> list[int]:
    n = len(lows)
    raw = []
    for i in range(k, n - k):
        if lows[i] == min(lows[i - k : i + k + 1]):
            raw.append(i)
    merged = []
    for i in raw:
        if merged and i - merged[-1] < k:
            if lows[i] < lows[merged[-1]]:
                merged[-1] = i
        else:
            merged.append(i)
    return merged


def legacy_detect_double_bottom(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    vols: Sequence[float],
    min_price: float = MIN_PRICE,
    min_dollar_vol: float = MIN_DOLLAR_VOL,
    min_bars: int = MIN_BARS,
    swing_k: int = SWING_K,
    recent: int = RECENT,
    min_gap: int = MIN_GAP,
    max_gap: int = MAX_GAP,
    tol_higher: float = TOL_HIGHER,
    tol_lower: float = TOL_LOWER,
    min_rally: float = MIN_RALLY,
    l2_low_zone: float = L2_LOW_ZONE,
    max_above_neck: float = MAX_ABOVE_NECK,
) -> dict | None:
    """旧脚本 detect_double_bottom 逐行复刻（参数可注入，供一致性比对）。"""
    n = len(closes)
    i_now = n - 1

    if closes[i_now] < min_price:
        return None
    dv = sum(closes[j] * vols[j] for j in range(max(0, n - 20), n)) / min(20, n)
    if dv < min_dollar_vol:
        return None

    sl = _swing_lows(lows, k=swing_k)
    if len(sl) < 2:
        return None

    dif, dea, hist = _macd(closes)
    rsi = _rsi_series(closes)
    low_60 = min(lows[max(0, n - 60) :])

    best = None
    for a in range(len(sl) - 1):
        i1 = sl[a]
        for b in range(a + 1, len(sl)):
            i2 = sl[b]
            gap = i2 - i1
            if gap < min_gap or gap > max_gap:
                continue
            if i_now - i2 > recent:
                continue
            l1, l2 = lows[i1], lows[i2]
            if l2 > low_60 * l2_low_zone:
                continue
            diff = (l2 - l1) / l1
            if diff > tol_higher or diff < -tol_lower:
                continue
            neck_i = max(range(i1, i2 + 1), key=lambda j: highs[j])
            neck = highs[neck_i]
            base = max(l1, l2)
            rally = (neck - base) / base
            if rally < min_rally:
                continue
            if closes[i_now] > neck * (1 + max_above_neck):
                continue

            dif_up = dif[i2] > dif[i1]
            hist_up = hist[i2] > hist[i1]
            rsi_up = rsi[i2] > rsi[i1]
            if not dif_up:
                continue
            div_cnt = sum([dif_up, hist_up, rsi_up])
            if div_cnt < 2:
                continue

            def vol_at(idx):
                s = max(0, idx - 1)
                seg = vols[s : idx + 2]
                return sum(seg) / len(seg) if seg else 0

            v1, v2 = vol_at(i1), vol_at(i2)
            vol_shrink = v2 / v1 if v1 > 0 else None

            score = 0
            score += max(0, 20 - abs(diff) * 300)
            score += div_cnt * 12
            if dif_up:
                score += 6
            if vol_shrink and vol_shrink < 0.8:
                score += 14
            elif vol_shrink and vol_shrink < 1.0:
                score += 8
            elif vol_shrink and vol_shrink > 1.3:
                score -= 8
            score += min(rally * 60, 14)
            score += max(0, 10 - (i_now - i2) * 0.3)
            if closes[i_now] > closes[i2]:
                score += 6

            if best is None or score > best["score"]:
                best = {
                    "score": score,
                    "i1": i1, "i2": i2, "neck_i": neck_i,
                    "l1": l1, "l2": l2, "neck": neck,
                    "diff_pct": diff * 100,
                    "gap": gap,
                    "bars_since_l2": i_now - i2,
                    "rally_pct": rally * 100,
                    "dif1": dif[i1], "dif2": dif[i2],
                    "hist1": hist[i1], "hist2": hist[i2],
                    "rsi1": rsi[i1], "rsi2": rsi[i2],
                    "dif_up": dif_up, "hist_up": hist_up, "rsi_up": rsi_up,
                    "div_cnt": div_cnt,
                    "vol_shrink": vol_shrink,
                }

    if not best:
        return None

    close_now = closes[i_now]
    neck = best["neck"]
    high_1y = max(highs)
    best.update({
        "close": close_now,
        "to_neck_pct": (close_now / neck - 1) * 100,
        "from_l2_pct": (close_now / best["l2"] - 1) * 100,
        "drawdown_pct": (close_now / high_1y - 1) * 100,
        "dif_now": dif[i_now],
        "dea_now": dea[i_now],
        "macd_water": dif[i_now] > 0,
        "rsi_now": rsi[i_now],
        "dollar_vol_m": dv / 1e6,
        "macd_cross": dif[i_now] > dea[i_now],
        "hist_now": hist[i_now],
        "hist_red": hist[i_now] > 0,
    })
    if close_now > neck * 1.02:
        best["stage"] = "已突破"
    elif close_now >= neck * 0.98:
        best["stage"] = "突破中"
    elif close_now >= best["l2"] * 1.03:
        best["stage"] = "右底爬升"
    else:
        best["stage"] = "右底构筑"

    dd = -best["drawdown_pct"]
    if 25 <= dd <= 40:
        best["score"] += 12
        best["dd_sweet"] = True
    elif 15 <= dd < 25 or 40 < dd <= 50:
        best["score"] += 5
        best["dd_sweet"] = False
    else:
        best["dd_sweet"] = False
    return best
