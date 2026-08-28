'use client'

import { useEffect, useState } from 'react'

import { get } from '@/lib/http/request'
import type { ApiResponse, Signal } from './types'

/**
 * 执行（或读取）指定策略在某天的扫描结果。返回 { data, loading, error }。
 */
export default function useScan(strategy: string | null, date: string) {
  const [data, setData] = useState<Signal[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!strategy || !date) return

    let cancelled = false
    setLoading(true)
    setError(null)

    get<ApiResponse<{ strategy: string; date: string; signals: Signal[] }>>(
      `/strategies/${strategy}/scan?date=${date}`
    ).then(([err, res]) => {
      if (cancelled) return
      if (err || !res || !res.body) {
        setError(err instanceof Error ? err.message : '加载失败')
        setData([])
      } else {
        setData(res.body.signals)
      }
      setLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [strategy, date])

  return { data, loading, error }
}
