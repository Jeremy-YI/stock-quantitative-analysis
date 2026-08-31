'use client'

import { useEffect, useState } from 'react'

import { get } from '@/lib/http/request'

import type { ApiResponse, CandlesBody } from './types'

/**
 * 拉个股日 K 线。
 * limit = 只取最后 N 个交易日（默认由调用方给，图上一般 1~2 个月）；
 * 不传则拿全量（几年的数据，只在「全部」视图用）。
 */
export default function useCandles(symbol: string, limit?: number) {
  const [data, setData] = useState<CandlesBody | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!symbol) return
    let cancelled = false
    setLoading(true)
    setError(null)

    const qs = limit ? `&limit=${limit}` : ''
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
  }, [symbol, limit])

  return { data, loading, error }
}
