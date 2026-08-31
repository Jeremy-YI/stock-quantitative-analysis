/** 个股详情契约（K 线 + 战法信号，与后端 schemas/indicator.py、schemas/sector.py 对齐）。 */

import type { ApiResponse } from '@/features/indicators/types'

export type { ApiResponse }

/** 一根日 K 线。 */
export interface CandlePoint {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount: number
}

export interface CandlesBody {
  symbol: string
  name: string
  series: CandlePoint[]
}

/** 一条战法信号（与 packages/strategies 的 Signal 对齐）。 */
export interface Signal {
  symbol: string
  strategy: string
  signal_type: string
  score: number
  triggered_at: string
  metrics: Record<string, number | string | boolean | null>
}

/** 按股票聚合的推荐条目（带证券简称）。 */
export interface RecommendedStock {
  symbol: string
  name: string
  score: number
  signals: Signal[]
  ratings: string[]
}

export interface ExcludedStock {
  symbol: string
  name: string
  reasons: string[]
}

export interface StockSignalsBody {
  sector: string
  date: string
  signals: Signal[]
  stocks: RecommendedStock[]
  excluded_st: number
  names_available: boolean
  strategies_used: string[]
  strategies_blocked: string[]
  ratings_available: boolean
  /** 当日命中的风控项（放量长上影 / 放量阴线 / 追高…） */
  excluded_risk: ExcludedStock[]
}
