/** 板块个股推荐契约（与后端 schemas/sector.py 对齐）。 */

import type { Signal } from '@/features/strategies/types'

export interface SectorInfo {
  name: string
  stock_count: number
}

export interface SectorListBody {
  sectors: SectorInfo[]
}

/** 按股票聚合的推荐条目（后端已带证券简称）。 */
export interface RecommendedStock {
  symbol: string
  name: string
  score: number
  signals: Signal[]
}

export interface RecommendationsBody {
  sector: string
  date: string
  signals: Signal[]
  stocks: RecommendedStock[]
  /** 因风险警示（ST/退市）被剔除的股票数 */
  excluded_st: number
  /** 名称快照是否可用（false 时未做 ST 过滤） */
  names_available: boolean
}

export type { Signal }
