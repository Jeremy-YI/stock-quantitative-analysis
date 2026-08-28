'use client'

import { useEffect, useState } from 'react'

import { get } from '@/lib/http/request'

import type { ApiResponse, MacdBody } from './types'

/**
 * 拉取 MACD 指标数据。默认代码 600519（贵州茅台）。
 * 返回 { data, loading, error }，组件据此渲染图表 / 骨架屏 / 错误提示。
 */
export default function useMacd(symbol: string) {
  const [data, setData] = useState<MacdBody | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!symbol) return

    let cancelled = false
    setLoading(true)
    setError(null)

    get<ApiResponse<MacdBody>>(`/indicators/macd?symbol=${symbol}`).then(
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
