'use client'

import { useEffect, useState } from 'react'

import { get } from '@/lib/http/request'

import type { ResearchSummary } from './types'

/**
 * 因子研究页数据 hook：拉离线快照（单因子超额表 / 交叉矩阵 / regime 分层）。
 */
export default function useResearch() {
  const [data, setData] = useState<ResearchSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    get<{ message: string; body: ResearchSummary }>('/research').then(([err, res]) => {
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
  }, [])

  return { data, loading, error }
}
