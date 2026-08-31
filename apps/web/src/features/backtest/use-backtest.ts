'use client'

import { useState } from 'react'

import { post } from '@/lib/http/request'

import type { BacktestRun, BacktestRunRequest } from './types'

/**
 * 发起回测并返回完整报告。返回 { data, loading, error }。
 */
export default function useBacktest() {
  const [data, setData] = useState<BacktestRun | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async (request: BacktestRunRequest) => {
    setLoading(true)
    setError(null)
    setData(null)

    const [err, res] = await post<{ message: string; body: BacktestRun }>('/backtest/runs', request)
    if (err || !res || !res.body) {
      setError(err instanceof Error ? err.message : '回测失败')
      setData(null)
    } else {
      setData(res.body)
    }
    setLoading(false)
  }

  return { data, loading, error, run }
}
