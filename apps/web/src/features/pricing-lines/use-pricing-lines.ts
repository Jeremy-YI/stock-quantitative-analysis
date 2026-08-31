'use client'

import { useEffect, useState } from 'react'

import { get } from '@/lib/http/request'
import type { ApiResponse } from '@/features/indicators/types'

import type { PricingLinesBody } from './types'

/**
 * 拉取三条定价线（生命线 / 阴量定价线 / 进攻K防线）序列。
 */
export default function usePricingLines(symbol: string) {
  const [data, setData] = useState<PricingLinesBody | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!symbol) return

    let cancelled = false
    setLoading(true)
    setError(null)

    get<ApiResponse<PricingLinesBody>>(`/indicators/pricing-lines?symbol=${symbol}`).then(
      ([err, res]) => {
        if (cancelled) return
        if (err || !res || !res.body) {
          setError(err instanceof Error ? err.message : '加载失败')
          setData(null)
        } else {
          setData(res.body)
        }
        setLoading(false)
      },
    )

    return () => {
      cancelled = true
    }
  }, [symbol])

  return { data, loading, error }
}
