/** 因子研究页契约（与后端 apps/api/src/schemas/research.py 对齐）。 */

import type { ApiResponse } from '@/features/indicators/types'

export type { ApiResponse }

export interface ResearchBinRow {
  factor: string
  label: string
  n: number
  win_rate: number
  avg_return: number
  excess_win_rate: number | null
  excess_return: number | null
}

export interface ResearchCrossCell {
  row: string
  col: string
  n: number
  win_rate: number
  excess_win_rate: number | null
}

export interface ResearchRegimeLayer {
  dimension: string
  label: string
  baseline_win_rate: number
  trend_n: number
  trend_excess: number | null
  reversion_n: number
  reversion_excess: number | null
}

export interface ResearchSummary {
  as_of: string | null
  sample: number
  hold_days: number
  baseline_win_rate: number | null
  single_factors: ResearchBinRow[]
  cross_matrix: ResearchCrossCell[]
  regime_layers: ResearchRegimeLayer[]
}
