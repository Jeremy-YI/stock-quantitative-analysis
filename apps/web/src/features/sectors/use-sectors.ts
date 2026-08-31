'use client'

/**
 * 拉取板块资金流数据。days 变化时自动重新请求。
 * 返回 { data, loading, error }。
 */
import { useEffect, useState } from 'react'

import { get } from '@/lib/http/request'
import type { ApiResponse, SectorFlowBody } from './types'

export default function useSectors(days: string) {
  const [data, setData] = useState<SectorFlowBody | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    get<ApiResponse<SectorFlowBody>>(`/sectors/flow?days=${encodeURIComponent(days)}`).then(
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
  }, [days])

  return { data, loading, error }
}
