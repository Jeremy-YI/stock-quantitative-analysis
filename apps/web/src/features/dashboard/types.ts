/** 概览页契约（与后端 apps/api/src/schemas/dashboard.py 对齐）。 */

import type { ApiResponse } from '@/features/indicators/types'
import type { Run } from '@/features/scheduler/types'

export type { ApiResponse }

export interface DashboardStrategy {
  name: string
  description: string
  signals_today: number
  selectivity: number | null
  excess_win_rate: number | null
  hold_days: number
}

export interface DashboardBaselineHold {
  hold_days: number
  win_rate: number
  avg_return: number
}

export interface DashboardBaseline {
  universe: string
  size: number
  holds: DashboardBaselineHold[]
}

export interface DashboardLastScan {
  status: string
  as_of: string | null
  duration_seconds: number | null
  symbols_scanned: number | null
}

export interface DashboardRegime {
  as_of: string | null
  index_20d_return: number | null
  activity: number | null
  drawdown: number | null
  index_20d_label: string
  activity_label: string
  drawdown_label: string
  allow_open: boolean | null
}

export interface DashboardOverview {
  as_of: string | null
  strategies: DashboardStrategy[]
  baselines: DashboardBaseline[]
  last_scan: DashboardLastScan | null
  regime: DashboardRegime | null
  recent_runs: Run[]
}
