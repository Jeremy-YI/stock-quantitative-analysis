"""组合回测：按策略信号建仓 → 固定持有期 / 止盈止损离场 → 净值曲线。

A股约束全部落实：

    - T+1：当日买入（开盘成交）次日才能卖出，卖出判断跳过建仓当日。
    - 涨跌停：开盘一字涨停买不进，收盘封跌停卖不出（见 ``execution``）。
    - 交易成本：佣金 / 印花税 / 过户费 / 滑点（见 ``CostConfig``）。
    - 仓位：单只 ≤ position_weight，最多动用 (1 - reserve_ratio) 资金，保留预备队。

仓位分配（阶段 8 修复 FIFO 缺陷）：

    - **按策略分资金池**：当日可用资金按策略份额（share，归一化到 sum=1）切分，
      各策略只能在自己的池子里建仓，互不抢占——避免旧版按信号到达顺序（FIFO）
      让信号量大的策略（如 b1b2b3 每日 3186 条）先占满仓位槽。
    - **策略内按 score 排序取前 N**：同一策略内信号按 ``Signal.score`` 降序，
      依次建仓直到该策略资金池耗尽，而非按遍历顺序。
    - 个股单只 ≤ position_weight；同日同标的只建一笔（跨策略去重，权重高者优先，
      再按 score）。
    - 市场环境过滤（可选）：``PortfolioConfig.regime_filter`` 给定后，只允许在
      ``market.regime`` 判定的允许市场状态下开仓（卖出不受限制）。

简化说明（文档记录在 docs/回测迁移说明.md）：
    - 3-2-2-2 分步建仓未实现，当前按一次性建仓近似（PortfolioConfig TODO）。
    - 止盈止损按收盘价判断（不用盘中高低点），属于保守近似。
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from market.calendar import trading_days
from market.regime import snapshot_at

from .config import BacktestConfig, default_config
from .execution import apply_slippage, buy_cost, can_buy_at_open, can_sell_at_close, sell_cost
from .stats import max_drawdown, sharpe_ratio, total_return

# 建仓日到可以卖出的最早间隔（交易日）：T+1 约束
_T1_DAYS = 1


def _eligible_strategies(signals: list, weights: dict[str, float] | None) -> set[str]:
    """返回参与建仓的策略集合（有信号且权重 > 0；等权时 = 所有出现过的策略）。"""
    present = {s.strategy for s in signals}
    if not weights:
        return present
    return {n for n in present if weights.get(n, 0.0) > 0}


def _strategy_shares(
    weights: dict[str, float] | None, eligible: set[str]
) -> dict[str, float]:
    """返回归一化到 sum=1 的策略资金份额。

    - weights 为 None 或空 → 等权（每个策略 1/N）。
    - weights 非空 → share = max(0, w) / sum(max(0, w))。
    """
    if not eligible:
        return {}
    if not weights:
        return {n: 1.0 / len(eligible) for n in eligible}
    raw = {n: max(0.0, float(weights.get(n, 0.0))) for n in eligible}
    total = sum(raw.values())
    if total <= 0:
        return {}
    return {n: raw[n] / total for n in raw}


def _strategy_priority(strategy: str, weights: dict[str, float] | None) -> float:
    """跨策略去重时的优先级：权重高者优先；等权时所有策略同优先级（再按 score）。"""
    if not weights:
        return 0.0
    return weights.get(strategy, 0.0)


def _better_signal(a, b, weights: dict[str, float] | None) -> bool:
    """跨策略去重：a 是否优于 b（先比权重，再比 score）。"""
    pa = _strategy_priority(a.strategy, weights)
    pb = _strategy_priority(b.strategy, weights)
    if pa != pb:
        return pa > pb
    return a.score > b.score


def _build_buy_groups(
    signals: list, weights: dict[str, float] | None, ord_map: dict[date, int]
) -> dict[date, dict[str, list]]:
    """把信号归组成 {entry_day: {strategy: [Signal 按 score 降序]}}。

    跨策略同日同标的去重（保留权重高/score 高者），策略内按 score 降序。
    """
    eligible = _eligible_strategies(signals, weights)
    day_candidates: dict[date, dict[str, object]] = {}
    for s in signals:
        if s.strategy not in eligible:
            continue
        entry_day = _next_trading_day(s.triggered_at)
        if entry_day not in ord_map:
            continue
        cand = day_candidates.setdefault(entry_day, {})
        existing = cand.get(s.symbol)
        if existing is None or _better_signal(s, existing, weights):
            cand[s.symbol] = s

    buys_by_day: dict[date, dict[str, list]] = {}
    for entry_day, cand in day_candidates.items():
        by_strat: dict[str, list] = {}
        for sig in cand.values():
            by_strat.setdefault(sig.strategy, []).append(sig)
        for lst in by_strat.values():
            lst.sort(key=lambda s: s.score, reverse=True)
        buys_by_day[entry_day] = by_strat
    return buys_by_day


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
    regime_series: pd.DataFrame | None = None,
) -> dict:
    """按信号模拟组合，返回净值曲线与汇总指标。

    Args:
        signals: Signal 列表（含 symbol / triggered_at / strategy / score）。
        candles: {symbol: 全量日线 DataFrame}（含 date/open/high/low/close）。
        config: 回测配置。
        regime_series: 市场环境序列（market.regime.compute_market_series 的输出，
            以 date 为索引）。仅在 ``config.portfolio.regime_filter`` 给定且本参数
            非空时生效；生效后只允许在允许的市场状态下开仓（卖出不受限）。

    Returns:
        dict，含：
            equity_curve: list[{date, equity}]
            total_return / max_drawdown / sharpe
            trade_count: 实际成交的买卖对数
            filled_buys: 成功买入次数
            skipped_buys: 因涨停/资金不足/regime 过滤跳过的买入次数
    """
    cfg = config or default_config()
    pcfg = cfg.portfolio
    rfilter = pcfg.regime_filter

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

    if not signals:
        return _empty_report(cfg)

    signal_dates = sorted({s.triggered_at for s in signals})
    min_date = signal_dates[0]
    max_date = signal_dates[-1]

    # 交易日序列 + 序数映射（持有期按交易日计）
    start = min_date
    end_ext = max_date
    for _ in range(pcfg.max_holding_days + 2):
        nxt = _next_trading_day(end_ext)
        if nxt == end_ext:
            break
        end_ext = nxt
    days = trading_days(start, end_ext)

    ord_map: dict[date, int] = {d: i for i, d in enumerate(days)}

    # 策略份额 + 按日归组买入信号（策略内按 score 降序）
    eligible = _eligible_strategies(signals, pcfg.strategy_weights)
    shares = _strategy_shares(pcfg.strategy_weights, eligible)
    buys_by_day = _build_buy_groups(signals, pcfg.strategy_weights, ord_map)

    cash = pcfg.initial_cash
    positions: dict[str, Position] = {}
    equity_curve: list[dict] = []
    filled_buys = 0
    skipped_buys = 0
    trades = 0

    for day in days:
        ord_i = ord_map[day]

        # 0) 市场环境过滤：不在允许状态时当日不开仓（卖出不受限）
        regime_ok = True
        if rfilter is not None:
            snap = snapshot_at(regime_series, day) if regime_series is not None else None
            if snap is None or not rfilter.allow(
                snap.index_20d_return, snap.activity, snap.drawdown
            ):
                regime_ok = False

        # 1) 买入（当日开盘，处理「昨日触发」的信号）
        if regime_ok:
            day_buys = buys_by_day.get(day, {})
            if day_buys:
                equity_now = _mark_to_market(cash, positions, close_map, day)
                deployable_cap = equity_now * (1.0 - pcfg.reserve_ratio)
                deployed_mv = _deployed(positions, close_map, day)
                headroom = max(deployable_cap - deployed_mv, 0.0)

                for strategy in sorted(day_buys.keys()):
                    share = shares.get(strategy, 0.0)
                    if share <= 0:
                        continue
                    pool = headroom * share
                    remaining_pool = pool
                    for sig in day_buys[strategy]:
                        symbol = sig.symbol
                        if symbol in positions:
                            continue
                        if remaining_pool <= 0:
                            break
                        o = open_map.get(symbol, {}).get(day)
                        pc = prev_close_map.get(symbol, {}).get(day)
                        if o is None or pc is None or o <= 0:
                            skipped_buys += 1
                            continue
                        if not can_buy_at_open(o, pc, symbol):
                            skipped_buys += 1
                            continue

                        # 单只仓位上限 / 该策略剩余资金池 / 可用现金 三者取最小
                        budget = min(equity_now * pcfg.position_weight, remaining_pool, cash)
                        if budget <= 0:
                            break

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
                        remaining_pool -= turnover
                        filled_buys += 1
        else:
            skipped_buys += sum(
                len(lst) for lst in buys_by_day.get(day, {}).values()
            )

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
