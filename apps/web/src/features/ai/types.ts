/** AI 解读契约（与后端 schemas/ai.py 对齐）。 */

import type { Signal } from '@/features/strategies/types'

export interface InterpretResult {
  symbol: string
  signals: Signal[]
  interpretation: string
}

export type { Signal }
