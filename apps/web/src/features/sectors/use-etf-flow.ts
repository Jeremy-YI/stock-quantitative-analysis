'use client'

/**
 * 拉取 ETF 资金流排行（净流入 / 净流出 TOP N）。
 * 数据来自 data/etf_flow.json 快照（scripts/fetch_etf_flow.py 收盘后落盘）。
 */
import { useEffect, useState } from 'react'

import { get } from '@/lib/http/request'

import type { ApiResponse, EtfFlowBody } from './types'

export default function useEtfFlow(top = 15) {
  const [data, setData] = useState<EtfFlowBody | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    get<ApiResponse<EtfFlowBody>>(`/sectors/etf-flow?top=${top}`).then(([err, res]) => {
      if (cancelled) return
      if (err || !res || !res.body) {
        setError(err instanceof Error ? err.message : '加载失败')
        setData(null)
      } else {
        setData(res.body)
      }
      setLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [top])

  return { data, loading, error }
}
