/** 策略层契约（与后端 apps/api/src/schemas/strategy.py 对齐）。 */

import type { ApiResponse } from '@/features/indicators/types'

export type { ApiResponse }

export interface StrategyInfo {
  name: string
  label: string  // 简短中文名（展示用）
  description: string
  config: Record<string, unknown>
  config_schema: Record<string, unknown>
}

export interface Signal {
  symbol: string
  strategy: string
  signal_type: string
  score: number
  triggered_at: string
  metrics: Record<string, number | string | boolean | null>
}

export interface StrategyListBody {
  strategies: StrategyInfo[]
}

export interface ScanBody {
  strategy: string
  date: string
  signals: Signal[]
}
