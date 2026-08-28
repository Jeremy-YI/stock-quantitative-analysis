'use client'

import { useEffect, useState } from 'react'

import { get } from '@/lib/http/request'
import type { ApiResponse } from '@/features/indicators/types'

import type { KdjBody } from './types'

/**
 * 拉取 KDJ 指标数据。返回 { data, loading, error }。
 */
export default function useKdj(symbol: string) {
  const [data, setData] = useState<KdjBody | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!symbol) return

    let cancelled = false
    setLoading(true)
    setError(null)

    get<ApiResponse<KdjBody>>(`/indicators/kdj?symbol=${symbol}`).then(
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
