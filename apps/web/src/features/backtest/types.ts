/** 回测层契约（与后端 apps/api/src/schemas/backtest.py + backtest/models.py 对齐）。 */

import type { ApiResponse } from '@/features/indicators/types'

export type { ApiResponse }

export interface HistogramBin {
  lower: number
  upper: number
  count: number
}

export interface HoldReturn {
  hold_days: number
  n: number
  win_rate: number
  avg_return: number
  median_return: number
  profit_loss_ratio: number | null
  std: number
  best: number
  worst: number
  quantiles: Record<string, number>
  histogram: HistogramBin[]
}

export interface StrategyResult {
  strategy: string
  holds: HoldReturn[]
}

export interface BoardResult {
  board: string
  holds: HoldReturn[]
}

export interface DecayPoint {
  date: string
  window: number
  win_rate: number
  n: number
}

export interface DecaySeries {
  strategy: string
  hold_days: number
  window: number
  points: DecayPoint[]
}

export interface VerificationReport {
  total_signals: number
  hold_days: number[]
  by_strategy: StrategyResult[]
  by_board: BoardResult[]
  decay: DecaySeries[]
}

export interface EquityPoint {
  date: string
  equity: number
}

export interface PortfolioReport {
  equity_curve: EquityPoint[]
  total_return: number
  max_drawdown: number
  sharpe: number | null
  trade_count: number
  filled_buys: number
  skipped_buys: number
  open_positions: number
}

export interface BacktestReport {
  verification: VerificationReport
  portfolio: PortfolioReport | null
}

export interface BacktestRun {
  run_id: string
  strategy: string | null
  start: string
  end: string
  mode: string
  report: BacktestReport
}

export interface BacktestRunRequest {
  strategy: string | null
  start: string
  end: string
  mode: string
}
