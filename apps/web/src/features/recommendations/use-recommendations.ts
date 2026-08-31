'use client'

import { useEffect, useState } from 'react'

import { get } from '@/lib/http/request'
import type { ApiResponse } from '@/features/indicators/types'

import type { RecommendationsBody, SectorListBody } from './types'

/** 拉取板块列表（用于下拉选择）。 */
export function useSectorList() {
  const [sectors, setSectors] = useState<string[]>([])
  useEffect(() => {
    get<ApiResponse<SectorListBody>>('/sectors').then(([err, res]) => {
      if (!err && res?.body) setSectors(res.body.sectors.map((s) => s.name))
    })
  }, [])
  return sectors
}

/** 拉取某板块的个股推荐（成分股 × 战法信号）。 */
export function useRecommendations(sector: string, date: string) {
  const [data, setData] = useState<RecommendationsBody | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!sector) return
    let cancelled = false
    setLoading(true)
    setError(null)

    get<ApiResponse<RecommendationsBody>>(
      `/sectors/${encodeURIComponent(sector)}/recommendations?date=${date}`,
    ).then(([err, res]) => {
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
  }, [sector, date])

  return { data, loading, error }
}
