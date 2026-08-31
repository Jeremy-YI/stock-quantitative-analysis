'use client'

import { useEffect, useState } from 'react'

import { get } from '@/lib/http/request'
import type { ApiResponse, StrategyInfo } from './types'

/**
 * 拉取可用策略列表。返回 { data, loading, error }。
 */
export default function useStrategies() {
  const [data, setData] = useState<StrategyInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    get<ApiResponse<{ strategies: StrategyInfo[] }>>('/strategies').then(([err, res]) => {
      if (cancelled) return
      if (err || !res || !res.body) {
        setError(err instanceof Error ? err.message : '加载失败')
        setData([])
      } else {
        setData(res.body.strategies)
      }
      setLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [])

  return { data, loading, error }
}
