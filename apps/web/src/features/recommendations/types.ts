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
  /** 触发策略的回测评级（robust / oos_positive / regime / insufficient / no_edge / overfit） */
  ratings: string[]
}

/** 被风控剔除的标的（透明展示，不静默丢弃）。 */
export interface ExcludedStock {
  symbol: string
  name: string
  reasons: string[]
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
  /** 本次实际参与的策略（回测过关的） */
  strategies_used: string[]
  /** 因回测不过关被挡掉的策略 */
  strategies_blocked: string[]
  /** 评级表是否可用 */
  ratings_available: boolean
  /** 被风控剔除的标的及原因 */
  excluded_risk: ExcludedStock[]
}

export type { Signal }
