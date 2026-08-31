'use client'

import { useEffect, useState } from 'react'

import { get } from '@/lib/http/request'
import type { ApiResponse } from '@/features/indicators/types'

import type { NewsBody, NewsDetailBody } from './types'

/** 拉取最新消息（财经日报）。 */
export default function useNews() {
  const [data, setData] = useState<NewsBody | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    get<ApiResponse<NewsBody>>('/news').then(([err, res]) => {
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

/** 拉取单条消息详情（全文 + 相关标的 + 相关消息）。 */
export function useNewsDetail(id: string) {
  const [data, setData] = useState<NewsDetailBody | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    get<ApiResponse<NewsDetailBody>>(`/news/${id}`).then(([err, res]) => {
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
