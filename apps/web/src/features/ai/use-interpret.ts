'use client'

import { useState } from 'react'

import { post } from '@/lib/http/request'
import type { ApiResponse } from '@/features/indicators/types'

import type { InterpretResult } from './types'

/** 触发 AI 解读。返回 { interpret, loading, error }。 */
export function useInterpret() {
  const [result, setResult] = useState<InterpretResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const interpret = async (symbol: string, date: string) => {
    setLoading(true)
    setError(null)
    setResult(null)
    const [err, res] = await post<ApiResponse<InterpretResult>>('/ai/interpret', {
      symbol,
      date,
    })
    if (err || !res || !res.body) {
      setError(err instanceof Error ? err.message : '解读失败')
    } else {
      setResult(res.body)
    }
    setLoading(false)
  }

  return { result, loading, error, interpret }
}
