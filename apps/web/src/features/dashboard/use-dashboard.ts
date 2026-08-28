'use client'

import { useEffect, useState } from 'react'

import { get } from '@/lib/http/request'

import type { DashboardOverview } from './types'

/**
 * 概览页数据 hook：拉 Dashboard 聚合数据（快照 + 调度器状态）。
 */
export default function useDashboard() {
  const [data, setData] = useState<DashboardOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    get<{ message: string; body: DashboardOverview }>('/dashboard/overview').then(
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
  }, [])

  return { data, loading, error }
}
