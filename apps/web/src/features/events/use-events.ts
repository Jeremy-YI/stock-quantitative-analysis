'use client'

import { useEffect, useState } from 'react'

import { get } from '@/lib/http/request'
import type { ApiResponse } from '@/features/indicators/types'

import type { EventsBody, EventDetailBody } from './types'

/** 拉取事件日历。 */
export default function useEvents() {
  const [data, setData] = useState<EventsBody | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    get<ApiResponse<EventsBody>>('/events').then(([err, res]) => {
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

/** 拉取单个事件详情（说明 + 历史数据）。 */
export function useEventDetail(id: string) {
  const [data, setData] = useState<EventDetailBody | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    get<ApiResponse<EventDetailBody>>(`/events/${id}`).then(([err, res]) => {
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
  }, [id])

  return { data, loading, error }
}
