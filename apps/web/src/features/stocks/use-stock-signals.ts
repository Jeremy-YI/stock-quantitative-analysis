'use client'

import { useEffect, useState } from 'react'

import { get } from '@/lib/http/request'

import type { ApiResponse, StockSignalsBody } from './types'

/** 拉单只个股在指定日的全部战法信号（买入信号列表 + K 线标记）。 */
export default function useStockSignals(symbol: string, date: string) {
  const [data, setData] = useState<StockSignalsBody | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!symbol || !date) return
    let cancelled = false
    setLoading(true)
    setError(null)

    get<ApiResponse<StockSignalsBody>>(`/stocks/${symbol}/signals?date=${date}`).then(
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
  }, [symbol, date])

  return { data, loading, error }
}
