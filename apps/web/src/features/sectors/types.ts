/** 板块资金流契约（与后端 apps/api/src/schemas/sector.py 对齐）。 */

import type { ApiResponse } from '@/features/indicators/types'

export type { ApiResponse }

/** 单个行业的资金流。金额单位：亿元。 */
export interface SectorFlow {
  sector: string
  etf: string | null  // 对应 ETF
  change_pct: number
  inflow: number
  outflow: number
  net: number
  companies: number
  leader: string
  leader_pct: number
  signal: string | null
}

/** 板块资金流响应体。 */
export interface SectorFlowBody {
  days: string
  top_inflow: SectorFlow[]
  top_outflow: SectorFlow[]
}
