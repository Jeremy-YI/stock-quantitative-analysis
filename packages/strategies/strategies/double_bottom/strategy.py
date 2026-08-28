"""双底反弹（W 底）策略：双底齐平 + 底背离 + 缩量二次探底。

复刻 `us_double_bottom.py` 的核心形态逻辑（摆动低点 → 配对左右底 → 颈线 →
底背离确认 → 量能确认 → 回撤甜点区），迁移到 A股口径：

    - 流动性：用 hsjday 自带 ``amount``（成交额，元）列，替代旧脚本的
      ``closes × volume``（美股口径的「美元成交额」近似）。
    - 交易约束：策略层只做形态识别，涨跌停 / T+1 / 前复权由 ``packages/backtest``
      （execution / portfolio）与 ``market.adjust`` 落实，这里不做重复处理。
    - 回撤基准：旧脚本 ``max(highs)`` 取全窗口，与「1 年高点」注释不符；新实现
      显式取近 ``drawdown_window`` 个交易日最高点。

与旧脚本的差异及理由详见 docs/双底反弹迁移说明.md。统一接口
``scan(candles, as_of, config) -> list[Signal]``。
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from indicators.macd import calc_macd
from indicators.rsi import calc_rsi
from strategies.double_bottom.config import DoubleBottomConfig, default_config
from strategies.filters import SymbolKind
from strategies.signal import Signal

NAME = "double_bottom"
DESCRIPTION = "双底齐平 + 底背离 + 缩量二次探底（W 底反弹型）"
SIGNAL_TYPE = "double_bottom"
TARGET_KINDS = (SymbolKind.STOCK,)

# ── 打分权重（内部常数，与旧脚本一致；阈值类参数已收敛到 config.py） ──
# 底部齐平度：越接近越好，满分 20，每偏离 1% 扣 3 分（20 - |diff|*300）
_SCORE_FLAT_FULL = 20.0
_SCORE_FLAT_SLOPE = 300.0
# 底背离：div_cnt（DIF/柱/RSI 抬升的个数）每项 12 分，DIF 抬升额外 +6
_SCORE_DIV_PER = 12.0
_SCORE_DIV_DIF_UP = 6.0
# 缩量二次探底：< 0.8 加 14，< 1.0 加 8，> 1.3 减 8
_SCORE_VOL_SHRINK = 14.0
_SCORE_VOL_MILD = 8.0
_SCORE_VOL_EXPAND_PENALTY = 8.0
# 颈线反弹幅度：rally*60 封顶 14
_SCORE_RALLY_SLOPE = 60.0
_SCORE_RALLY_CAP = 14.0
# 右底新鲜度：满分 10，每远离 1 根扣 0.3
_SCORE_RECENT_FULL = 10.0
_SCORE_RECENT_DECAY = 0.3
# 已在爬升（现价 > 右底）
_SCORE_CLIMBING = 6.0
# 回撤甜点区：25%~40% 加 12，15%~25% 或 40%~50% 加 5
_SCORE_DD_SWEET = 12.0
_SCORE_DD_NEAR = 5.0

# 底背离需要「DIF/柱/RSI 三项里至少 2 项抬升」才算有效背离
_DIV_MIN_COUNT = 2

# 低位区回看窗口（右底必须落在近 60 日最低价附近）
_LOW_ZONE_WINDOW = 60


def swing_lows(lows: list[float], k: int) -> list[int]:
    """找摆动低点（局部极小值）：左右各 k 根都不低于它，相邻的合并取更低。

    与旧脚本 ``swing_lows`` 逐行一致。返回低点索引列表（升序）。
    """
    n = len(lows)
    if n < 2 * k + 1:
        return []
    raw: list[int] = []
    for i in range(k, n - k):
        if lows[i] == min(lows[i - k : i + k + 1]):
            raw.append(i)
    # 合并相邻（距离 < k）的低点，保留更低的那个
    merged: list[int] = []
    for i in raw:
        if merged and i - merged[-1] < k:
            if lows[i] < lows[merged[-1]]:
                merged[-1] = i
        else:
            merged.append(i)
    return merged


def _vol_at(vols: list[float], idx: int, radius: int) -> float:
    """底部附近均量：取 idx 前后各 radius 根的平均成交量。"""
    s = max(0, idx - radius)
    seg = vols[s : idx + radius + 1]
    return sum(seg) / len(seg) if seg else 0.0


def _detect(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    vols: list[float],
    amounts: list[float],
    cfg: DoubleBottomConfig,
) -> dict | None:
    """对单只标的判定双底形态，返回评分明细 dict 或 None。"""
    n = len(closes)
    i_now = n - 1

    # 价格门槛（剔除仙股/低价股）
    if closes[i_now] < cfg.min_price:
        return None

    # 流动性门槛：近 20 日平均成交额（A股 amount 列，元）
    recent_amounts = amounts[max(0, n - 20) :]
    if not recent_amounts:
        return None
    avg_amount = sum(recent_amounts) / len(recent_amounts)
    if avg_amount < cfg.min_amount:
        return None

    sl = swing_lows(lows, cfg.swing_k)
    if len(sl) < 2:
        return None

    dif, dea, hist = calc_macd(closes)
    rsi = calc_rsi(closes)
    low_60 = min(lows[max(0, n - _LOW_ZONE_WINDOW) :])

    best: dict | None = None
    for a in range(len(sl) - 1):
        i1 = sl[a]
        for b in range(a + 1, len(sl)):
            i2 = sl[b]
            gap = i2 - i1
            if gap < cfg.min_gap or gap > cfg.max_gap:
                continue
            if i_now - i2 > cfg.recent:  # 右底太旧，不新鲜
                continue
            l1, l2 = lows[i1], lows[i2]
            if l2 > low_60 * cfg.l2_low_zone:  # 右底不在低位区 = 半山腰震荡
                continue
            diff = (l2 - l1) / l1 if l1 > 0 else 0.0
            if diff > cfg.tol_higher or diff < -cfg.tol_lower:
                continue

            # 颈线 = 两底之间的最高价
            neck_i = max(range(i1, i2 + 1), key=lambda j: highs[j])
            neck = highs[neck_i]
            base = max(l1, l2)
            rally = (neck - base) / base if base > 0 else 0.0
            if rally < cfg.min_rally:
                continue
            if closes[i_now] > neck * (1 + cfg.max_above_neck):  # 形态已走完
                continue

            # 底背离：DIF 抬升为硬条件
            dif_up = dif[i2] > dif[i1]
            hist_up = hist[i2] > hist[i1]
            rsi_up = rsi[i2] > rsi[i1]
            if not dif_up:
                continue
            div_cnt = sum((dif_up, hist_up, rsi_up))
            if div_cnt < _DIV_MIN_COUNT:
                continue

            # 量能：右底附近均量 vs 左底附近均量（缩量二次探底）
            v1 = _vol_at(vols, i1, cfg.vol_window)
            v2 = _vol_at(vols, i2, cfg.vol_window)
            vol_shrink = v2 / v1 if v1 > 0 else None

            score = 0.0
            # 齐平度（越接近越好，微破前低也可）
            score += max(0.0, _SCORE_FLAT_FULL - abs(diff) * _SCORE_FLAT_SLOPE)
            # 底背离最重要
            score += div_cnt * _SCORE_DIV_PER
            if dif_up:
                score += _SCORE_DIV_DIF_UP
            # 缩量二次探底
            if vol_shrink is not None:
                if vol_shrink < cfg.vol_shrink_threshold:
                    score += _SCORE_VOL_SHRINK
                elif vol_shrink < 1.0:
                    score += _SCORE_VOL_MILD
                elif vol_shrink > 1.3:
                    score -= _SCORE_VOL_EXPAND_PENALTY
            # 颈线反弹幅度
            score += min(rally * _SCORE_RALLY_SLOPE, _SCORE_RALLY_CAP)
            # 右底新鲜度
            score += max(0.0, _SCORE_RECENT_FULL - (i_now - i2) * _SCORE_RECENT_DECAY)
            # 已在爬升
            if closes[i_now] > closes[i2]:
                score += _SCORE_CLIMBING

            if best is None or score > best["score"]:
                best = {
                    "score": score,
                    "i1": i1,
                    "i2": i2,
                    "neck_i": neck_i,
                    "l1": l1,
                    "l2": l2,
                    "neck": neck,
                    "diff_pct": diff * 100.0,
                    "gap": gap,
                    "bars_since_l2": i_now - i2,
                    "rally_pct": rally * 100.0,
                    "dif1": dif[i1],
                    "dif2": dif[i2],
                    "hist1": hist[i1],
                    "hist2": hist[i2],
                    "rsi1": rsi[i1],
                    "rsi2": rsi[i2],
                    "dif_up": dif_up,
                    "hist_up": hist_up,
                    "rsi_up": rsi_up,
                    "div_cnt": div_cnt,
                    "vol_shrink": vol_shrink,
                }

    if not best:
        return None

    close_now = closes[i_now]
    neck = best["neck"]
    high_ref = max(highs[max(0, n - cfg.drawdown_window) :])
    best.update(
        {
            "close": close_now,
            "to_neck_pct": (close_now / neck - 1) * 100.0 if neck > 0 else 0.0,
            "from_l2_pct": (close_now / best["l2"] - 1) * 100.0 if best["l2"] > 0 else 0.0,
            "drawdown_pct": (close_now / high_ref - 1) * 100.0 if high_ref > 0 else 0.0,
            "dif_now": dif[i_now],
            "dea_now": dea[i_now],
            "macd_water": dif[i_now] > 0,
            "rsi_now": rsi[i_now],
            "avg_amount": avg_amount,
            "macd_cross": dif[i_now] > dea[i_now],
            "hist_now": hist[i_now],
            "hist_red": hist[i_now] > 0,
        }
    )

    # 阶段判定：已突破 > 突破中 > 右底爬升 > 右底构筑
    if close_now > neck * (1 + cfg.breakout_margin):
        best["stage"] = "已突破"
    elif close_now >= neck * (1 - cfg.breakout_margin):
        best["stage"] = "突破中"
    elif close_now >= best["l2"] * 1.03:
        best["stage"] = "右底爬升"
    else:
        best["stage"] = "右底构筑"

    # 回撤幅度加分（TOOLS.md：25%~40% 是最佳入场区）
    dd = -best["drawdown_pct"]
    if cfg.drawdown_low <= dd <= cfg.drawdown_high:
        best["score"] += _SCORE_DD_SWEET
        best["dd_sweet"] = True
    elif 15 <= dd < cfg.drawdown_low or cfg.drawdown_high < dd <= 50:
        best["score"] += _SCORE_DD_NEAR
        best["dd_sweet"] = False
    else:
        best["dd_sweet"] = False

    return best


def _evaluate(
    symbol: str, df: pd.DataFrame, as_of: date, cfg: DoubleBottomConfig
) -> Signal | None:
    """对单只标的判定双底反弹。不满足条件返回 None。"""
    if df is None or len(df) < cfg.min_bars:
        return None

    closes = df["close"].astype(float).tolist()
    highs = df["high"].astype(float).tolist()
    lows = df["low"].astype(float).tolist()
    vols = df["volume"].astype(float).tolist()
    amounts = df["amount"].astype(float).tolist()

    best = _detect(closes, highs, lows, vols, amounts, cfg)
    if best is None:
        return None

    # 颈线突破确认开关：开启时只出「已站上颈线」的确认信号
    if cfg.require_breakout and best["stage"] != "已突破":
        return None

    def r3(v: float) -> float:
        return round(float(v), 3)

    return Signal(
        symbol=symbol,
        strategy=NAME,
        signal_type=SIGNAL_TYPE,
        score=round(best["score"], 1),
        triggered_at=as_of,
        metrics={
            "stage": best["stage"],
            "l1": r3(best["l1"]),
            "l2": r3(best["l2"]),
            "neck": r3(best["neck"]),
            "diff_pct": r3(best["diff_pct"]),
            "gap": best["gap"],
            "bars_since_l2": best["bars_since_l2"],
            "rally_pct": r3(best["rally_pct"]),
            "to_neck_pct": r3(best["to_neck_pct"]),
            "from_l2_pct": r3(best["from_l2_pct"]),
            "drawdown_pct": r3(best["drawdown_pct"]),
            "div_cnt": best["div_cnt"],
            "dif_up": best["dif_up"],
            "hist_up": best["hist_up"],
            "rsi_up": best["rsi_up"],
            "vol_shrink": r3(best["vol_shrink"]) if best["vol_shrink"] is not None else None,
            "dif_now": r3(best["dif_now"]),
            "macd_water": best["macd_water"],
            "rsi_now": r3(best["rsi_now"]),
            "close": r3(best["close"]),
            "dd_sweet": best["dd_sweet"],
        },
    )


def scan(
    candles: dict[str, pd.DataFrame],
    as_of: date,
    config: DoubleBottomConfig | None = None,
) -> list[Signal]:
    """对一批日线扫描双底反弹信号。"""
    cfg = config or default_config()
    signals: list[Signal] = []

    for symbol in sorted(candles):
        df = candles[symbol]
        signal = _evaluate(symbol, df, as_of, cfg)
        if signal is not None:
            signals.append(signal)

    return signals
