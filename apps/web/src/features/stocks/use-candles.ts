'use client'

import { useEffect, useState } from 'react'

import { get } from '@/lib/http/request'

import type { ApiResponse, CandlesBody } from './types'

/** 拉个股日 K 线（可选起始日，默认后端给全量）。 */
export default function useCandles(symbol: string, start?: string) {
  const [data, setData] = useState<CandlesBody | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!symbol) return
    let cancelled = false
    setLoading(true)
    setError(null)

    const qs = start ? `&start=${start}` : ''
    get<ApiResponse<CandlesBody>>(`/indicators/candles?symbol=${symbol}${qs}`).then(
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
  }, [symbol, start])

  return { data, loading, error }
}
