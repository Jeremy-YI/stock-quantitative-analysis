'use client'

import { useEffect, useState } from 'react'

import { get } from '@/lib/http/request'
import type { ApiResponse } from '@/features/indicators/types'

import type { RsiBody } from './types'

/**
 * 拉取 RSI 指标数据。返回 { data, loading, error }。
 */
export default function useRsi(symbol: string) {
  const [data, setData] = useState<RsiBody | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!symbol) return

    let cancelled = false
    setLoading(true)
    setError(null)

    get<ApiResponse<RsiBody>>(`/indicators/rsi?symbol=${symbol}`).then(
      ([err, res]) => {
        if (cancelled) return
        if (err || !res || !res.body) {
          setError(err instanceof Error ? err.message : '加载失败')
          setData(null)
        } else {
          setData(res.body)
        }
        setLoading(false)
      }
    )

    return () => {
      cancelled = true
    }
  }, [symbol])

  return { data, loading, error }
}
