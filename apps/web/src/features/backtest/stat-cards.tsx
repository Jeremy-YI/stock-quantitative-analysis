'use client'

import type { BacktestRun } from './types'
import { statCard, statGrid, statLabel, statValue } from './backtest-styles'

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${(v * 100).toFixed(2)}%`
}

function pp(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}pp`
}

function colorClass(v: number | null | undefined): string {
  if (v === null || v === undefined) return 'text-foreground'
  if (v > 0) return 'text-up'
  if (v < 0) return 'text-down'
  return 'text-neutral'
}

export interface StatCardsProps {
  run: BacktestRun
}

/** 找出超额胜率最高（最正）的策略与持有期。 */
function bestExcess(run: BacktestRun) {
  let best: { strategy: string; value: number } | null = null
  for (const s of run.report.verification.by_strategy) {
    for (const h of s.holds) {
      if (h.excess_win_rate === null) continue
      if (best === null || h.excess_win_rate > best.value) {
        best = { strategy: s.strategy, value: h.excess_win_rate }
      }
    }
  }
  return best
}

/** 找出选择性最强（占比最小）的策略。 */
function bestSelectivity(run: BacktestRun) {
  let best: { strategy: string; value: number } | null = null
  for (const s of run.report.verification.by_strategy) {
    if (s.selectivity === null) continue
    if (best === null || s.selectivity < best.value) {
      best = { strategy: s.strategy, value: s.selectivity }
    }
  }
  return best
}

/** 回测统计指标卡片（总信号 / 组合收益 / 回撤 / 夏普 / 成交 / 建仓 / 超额 / 选择性）。 */
export default function StatCards({ run }: StatCardsProps) {
  const v = run.report.verification
  const p = run.report.portfolio
  const excess = bestExcess(run)
  const selectivity = bestSelectivity(run)

  return (
    <div className={statGrid}>
      <div className={statCard}>
        <div className={statLabel}>总信号数</div>
        <div className={statValue}>{v.total_signals}</div>
      </div>

      <div className={statCard}>
        <div className={statLabel}>组合总收益</div>
        <div className={`${statValue} ${colorClass(p?.total_return)}`}>
          {p ? pct(p.total_return) : '—'}
        </div>
      </div>

      <div className={statCard}>
        <div className={statLabel}>最大回撤</div>
        <div className={`${statValue} ${colorClass(p?.max_drawdown)}`}>
          {p ? pct(p.max_drawdown) : '—'}
        </div>
      </div>

      <div className={statCard}>
        <div className={statLabel}>夏普比率</div>
        <div className={statValue}>
          {p && p.sharpe !== null ? p.sharpe.toFixed(2) : '—'}
        </div>
      </div>

      <div className={statCard}>
        <div className={statLabel}>成交笔数</div>
        <div className={statValue}>{p ? p.trade_count : '—'}</div>
      </div>

      <div className={statCard}>
        <div className={statLabel}>建仓成功</div>
        <div className={statValue}>{p ? p.filled_buys : '—'}</div>
      </div>

      <div className={statCard}>
        <div className={statLabel}>
          最优超额胜率{excess ? ` (${excess.strategy})` : ''}
        </div>
        <div className={`${statValue} ${colorClass(excess?.value)}`}>
          {pp(excess?.value)}
        </div>
      </div>

      <div className={statCard}>
        <div className={statLabel}>
          最强选择性{selectivity ? ` (${selectivity.strategy})` : ''}
        </div>
        <div className={statValue}>
          {selectivity ? pct(selectivity.value) : '—'}
        </div>
      </div>
    </div>
  )
}
