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

/** 单只场内 ETF 的资金流。金额单位：亿元。 */
export interface EtfFlow {
  code: string
  name: string
  price: number
  change_pct: number
  /** 主力净流入（东财大单口径）；非交易日/历史不可回溯时为 null */
  net: number | null
  /** 主力净流入占成交额比 %；同上 */
  net_ratio: number | null
  turnover: number
  turnover_rate: number
  mcap: number
  /** 份额变化估算的净申购（亿），需隔日对比，首日为 null */
  share_net: number | null
}

/** 主题龙头 ETF：同一主题里资金最集中（流通市值最大）的那一只。 */
export interface EtfLeader extends EtfFlow {
  /** 大类：宽基 / 科技成长 / 医药消费 / 金融地产 / 周期资源 / 红利防御 / 跨境 */
  category: string
  /** 主题：半导体/芯片、红利低波… */
  theme: string
  /** 该主题下共有多少只 ETF（展示的是其中最大的） */
  peers: number
}

/** ETF 资金流响应体。 */
export interface EtfFlowBody {
  date: string
  total: number
  has_share_flow: boolean
  /** 大单口径是否可用（非交易日快照拿不到） */
  flow_available: boolean
  leaders: EtfLeader[]
  top_inflow: EtfFlow[]
  top_outflow: EtfFlow[]
}
