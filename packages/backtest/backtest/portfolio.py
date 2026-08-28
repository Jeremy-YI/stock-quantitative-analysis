"""组合回测：按策略信号建仓 → 固定持有期 / 止盈止损离场 → 净值曲线。

A股约束全部落实：

    - T+1：当日买入（开盘成交）次日才能卖出，卖出判断跳过建仓当日。
    - 涨跌停：开盘一字涨停买不进，收盘封跌停卖不出（见 ``execution``）。
    - 交易成本：佣金 / 印花税 / 过户费 / 滑点（见 ``CostConfig``）。
    - 仓位：单只 ≤ position_weight，最多动用 (1 - reserve_ratio) 资金，保留预备队。

简化说明（文档记录在 docs/回测迁移说明.md）：
    - 3-2-2-2 分步建仓未实现，当前按一次性建仓近似（PortfolioConfig TODO）。
    - 止盈止损按收盘价判断（不用盘中高低点），属于保守近似。
    - 同一天同一标的只建一笔；已持仓的标的当日新信号不重复加仓。
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from market.calendar import trading_days

from .config import BacktestConfig, default_config
from .execution import apply_slippage, buy_cost, can_buy_at_open, can_sell_at_close, sell_cost
from .stats import max_drawdown, sharpe_ratio, total_return

# 建仓日到可以卖出的最早间隔（交易日）：T+1 约束
_T1_DAYS = 1


def strategy_weight_multiplier(strategy: str, weights: dict[str, float] | None) -> float:
    """把策略权重归一化成仓位乘数（0~1）。

    - weights 为空 → 等权，返回 1.0（旧行为：每信号都按 position_weight 全额建仓）。
    - weights 非空 → 乘数 = w / max(w)，其中 w = weights.get(strategy, 0.0)。
      未列入的策略权重为 0（不建仓），权重最高的策略乘数 = 1.0（拿满单只仓位上限）。
    """
    if not weights:
        return 1.0
    max_w = max(weights.values()) if weights else 0.0
    if max_w <= 0:
        return 0.0
    return weights.get(strategy, 0.0) / max_w


def _strategy_rank(strategy: str, weights: dict[str, float] | None) -> float:
    """同日同标的多个策略信号时，取权重更高的策略（等权时权重相等，保留先见者）。"""
    if not weights:
        return 0.0
    return weights.get(strategy, 0.0)


class Position:
    """一笔持仓。"""

    __slots__ = ("symbol", "qty", "entry_price", "entry_ord")

    def __init__(self, symbol: str, qty: float, entry_price: float, entry_ord: int) -> None:
        self.symbol = symbol
        self.qty = qty
        self.entry_price = entry_price
        self.entry_ord = entry_ord


def simulate_portfolio(
    signals: list,
    candles: dict[str, pd.DataFrame],
    config: BacktestConfig | None = None,
) -> dict:
    """按信号模拟组合，返回净值曲线与汇总指标。

    Args:
        signals: Signal 列表（含 symbol / triggered_at / strategy）。
        candles: {symbol: 全量日线 DataFrame}（含 date/open/high/low/close）。
        config: 回测配置。

    Returns:
        dict，含：
            equity_curve: list[{date, equity}]
            total_return / max_drawdown / sharpe
            trade_count: 实际成交的买卖对数
            filled_buys: 成功买入次数
            skipped_buys: 因涨停/资金不足跳过的买入次数
    """
    cfg = config or default_config()
    pcfg = cfg.portfolio

    # 预取每日开盘/收盘价（按日期字典，供 O(1) 取用 + 停牌前向填充）
    open_map: dict[str, dict[date, float]] = {}
    close_map: dict[str, dict[date, float]] = {}
    prev_close_map: dict[str, dict[date, float]] = {}
    for symbol, df in candles.items():
        if df is None or df.empty:
            continue
        dates = df["date"].tolist()
        opens = df["open"].astype(float).tolist()
        closes = df["close"].astype(float).tolist()
        open_map[symbol] = dict(zip(dates, opens))
        close_map[symbol] = dict(zip(dates, closes))
        # 昨收（涨跌停基准）：前一根收盘
        pc: dict[date, float] = {}
        prev = None
        for d, c in zip(dates, closes):
            pc[d] = prev if prev is not None else c
            prev = c
        prev_close_map[symbol] = pc

    # 信号按交易日索引，方便「T 日收盘触发 → T+1 开盘买入」
    if not signals:
        return _empty_report(cfg)

    signal_dates = sorted({s.triggered_at for s in signals})
    min_date = signal_dates[0]
    max_date = signal_dates[-1]

    # 交易日序列 + 序数映射（持有期按交易日计）
    # 窗口：从信号首日开始，末端扩展 max_holding_days 个交易日
    start = min_date
    end = max_date
    end_ext = end
    for _ in range(pcfg.max_holding_days + 2):
        nxt = _next_trading_day(end_ext)
        if nxt == end_ext:
            break
        end_ext = nxt
    days = trading_days(start, end_ext)

    ord_map: dict[date, int] = {d: i for i, d in enumerate(days)}

    # 按「触发日 + 1」归组待买入信号（去重：同日同标的只建一笔，保留权重最高的策略）
    # 权重为 0 的策略（未列入 strategy_weights 或权重 ≤ 0）直接不建仓，不进候选。
    buys_by_day: dict[date, dict[str, str]] = {}
    for s in signals:
        if strategy_weight_multiplier(s.strategy, pcfg.strategy_weights) <= 0:
            continue
        entry_day = _next_trading_day(s.triggered_at)
        if entry_day not in ord_map:
            continue
        day_map = buys_by_day.setdefault(entry_day, {})
        existing = day_map.get(s.symbol)
        if existing is None or _strategy_rank(s.strategy, pcfg.strategy_weights) > _strategy_rank(
            existing, pcfg.strategy_weights
        ):
            day_map[s.symbol] = s.strategy

    cash = pcfg.initial_cash
    positions: dict[str, Position] = {}
    equity_curve: list[dict] = []
    filled_buys = 0
    skipped_buys = 0
    trades = 0

    for day in days:
        ord_i = ord_map[day]

        # 1) 买入（当日开盘，处理「昨日触发」的信号）
        for symbol, strategy in buys_by_day.get(day, {}).items():
            if symbol in positions:
                continue
            o = open_map.get(symbol, {}).get(day)
            pc = prev_close_map.get(symbol, {}).get(day)
            if o is None or pc is None or o <= 0:
                skipped_buys += 1
                continue
            if not can_buy_at_open(o, pc, symbol):
                skipped_buys += 1
                continue

            equity_now = _mark_to_market(cash, positions, close_map, day)
            deployable_cap = equity_now * (1.0 - pcfg.reserve_ratio)
            deployed_mv = _deployed(positions, close_map, day)
            # 单只仓位上限、可用现金、总部署上限（保留预备队）三者取最小
            base_budget = min(
                equity_now * pcfg.position_weight,
                cash,
                max(deployable_cap - deployed_mv, 0.0),
            )
            # 策略权重：base_budget × w / max(w)，权重高的策略拿满、低的等比例缩小
            budget = base_budget * strategy_weight_multiplier(
                strategy, pcfg.strategy_weights
            )

            buy_px = apply_slippage(o, "buy", cfg.cost)
            if buy_px <= 0:
                skipped_buys += 1
                continue
            qty = budget / buy_px
            turnover = buy_px * qty
            fee = buy_cost(turnover, symbol, cfg.cost)
            total_cost = turnover + fee
            if total_cost > cash + 1e-9 or qty <= 0:
                skipped_buys += 1
                continue

            cash -= total_cost
            positions[symbol] = Position(symbol, qty, buy_px, ord_i)
            filled_buys += 1

        # 2) 卖出（当日收盘，判断固定持有期 / 止盈止损，T+1 约束）
        for symbol in list(positions.keys()):
            pos = positions[symbol]
            if ord_i - pos.entry_ord < _T1_DAYS:
                continue  # T+1：建仓当日不能卖

            c = close_map.get(symbol, {}).get(day)
            pc = prev_close_map.get(symbol, {}).get(day)
            if c is None or pc is None:
                continue  # 停牌：跳过，顺延

            holding_days = ord_i - pos.entry_ord
            ret = c / pos.entry_price - 1.0 if pos.entry_price > 0 else 0.0
            hit_stop = ret <= pcfg.stop_loss_pct
            hit_take = ret >= pcfg.take_profit_pct
            hit_hold = holding_days >= pcfg.max_holding_days

            if not (hit_stop or hit_take or hit_hold):
                continue
            if not can_sell_at_close(c, pc, symbol):
                continue  # 跌停卖不出，顺延到下一日

            sell_px = apply_slippage(c, "sell", cfg.cost)
            turnover = sell_px * pos.qty
            fee = sell_cost(turnover, symbol, cfg.cost)
            cash += turnover - fee
            del positions[symbol]
            trades += 1

        # 3) 收盘净值
        equity_now = _mark_to_market(cash, positions, close_map, day)
        equity_curve.append({"date": day.isoformat(), "equity": round(equity_now, 2)})

    # 期末强制平仓（按末日收盘估值）
    final_day = days[-1]
    equity_final = _mark_to_market(cash, positions, close_map, final_day)

    eq = [p["equity"] for p in equity_curve]
    daily_returns = [(eq[i] / eq[i - 1] - 1.0) for i in range(1, len(eq)) if eq[i - 1] > 0]

    return {
        "equity_curve": equity_curve,
        "total_return": total_return([eq[0], equity_final]),
        "max_drawdown": max_drawdown(eq),
        "sharpe": sharpe_ratio(daily_returns, cfg.risk_free_rate),
        "trade_count": trades,
        "filled_buys": filled_buys,
        "skipped_buys": skipped_buys,
        "open_positions": len(positions),
    }


def _mark_to_market(
    cash: float,
    positions: dict[str, Position],
    close_map: dict[str, dict[date, float]],
    day: date,
) -> float:
    """按当日收盘估值总权益（停牌则用最近收盘前向填充）。"""
    total = cash
    for pos in positions.values():
        c = _close_as_of(close_map.get(pos.symbol, {}), day)
        if c is not None:
            total += pos.qty * c
    return total


def _deployed(
    positions: dict[str, Position],
    close_map: dict[str, dict[date, float]],
    day: date,
) -> float:
    """已占用市值（用持仓市值，供「保留预备队」上限判断）。"""
    deployed = 0.0
    for pos in positions.values():
        c = _close_as_of(close_map.get(pos.symbol, {}), day)
        if c is not None:
            deployed += pos.qty * c
    return deployed


def _close_as_of(close_by_date: dict[date, float], day: date) -> float | None:
    """取 <= day 的最近收盘价（前向填充，处理停牌）。"""
    if not close_by_date:
        return None
    if day in close_by_date:
        return close_by_date[day]
    # 找 <= day 的最大日期
    best = None
    for d, c in close_by_date.items():
        if d <= day and (best is None or d > best):
            best = d
    return close_by_date[best] if best is not None else None


def _next_trading_day(day: date) -> date:
    """下一个交易日（跳过周末 + 节假日）。"""
    from datetime import timedelta

    from market.calendar import is_trading_day

    d = day + timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def _empty_report(cfg: BacktestConfig) -> dict:
    """无信号时的空报告。"""
    return {
        "equity_curve": [],
        "total_return": 0.0,
        "max_drawdown": 0.0,
        "sharpe": None,
        "trade_count": 0,
        "filled_buys": 0,
        "skipped_buys": 0,
        "open_positions": 0,
    }
