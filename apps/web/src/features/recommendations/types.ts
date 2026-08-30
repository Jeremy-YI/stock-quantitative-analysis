/** 板块个股推荐契约（与后端 schemas/sector.py 对齐）。 */

import type { Signal } from '@/features/strategies/types'

export interface SectorInfo {
  name: string
  stock_count: number
}

export interface SectorListBody {
  sectors: SectorInfo[]
}

export interface RecommendationsBody {
  sector: string
  date: string
  signals: Signal[]
}

export type { Signal }
