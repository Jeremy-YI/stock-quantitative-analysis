'use client'

import { useEffect, useState } from 'react'

import { get } from '@/lib/http/request'
import type { ApiResponse } from '@/features/indicators/types'

export interface StrategyRatingWindow {
  excess_win_rate: number
  n: number
  selectivity: number | null
}

export interface StrategyRatingItem {
  label: string
  rating: string
  client_safe: boolean
  reason: string
  windows: Record<string, StrategyRatingWindow>
}

export interface StrategyRatingsBody {
  as_of: string
  source: string
  criteria: Record<string, unknown>
  strategies: Record<string, StrategyRatingItem>
}

/**
 * 拉策略回测评级表。
 * 推荐页用它决定哪些战法能给客户看，详情页用它给每条信号标评级，
 * root 回测页用它展示判定依据。
 */
export default function useStrategyRatings() {
  const [data, setData] = useState<StrategyRatingsBody | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    get<ApiResponse<StrategyRatingsBody>>('/strategies/ratings').then(([err, res]) => {
      if (cancelled) return
      if (!err && res?.body) setData(res.body)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [])

  return { data, loading }
}
