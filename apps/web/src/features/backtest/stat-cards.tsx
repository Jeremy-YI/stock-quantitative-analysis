'use client'

import type { BacktestRun } from './types'
import { statCard, statGrid, statLabel, statValue } from './backtest-styles'

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${(v * 100).toFixed(2)}%`
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

/** 回测统计指标卡片（总信号 / 组合收益 / 最大回撤 / 夏普 / 成交 / 建仓）。 */
export default function StatCards({ run }: StatCardsProps) {
  const v = run.report.verification
  const p = run.report.portfolio

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
    </div>
  )
}
