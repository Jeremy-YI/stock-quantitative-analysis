'use client'

import { useRef, useState } from 'react'

import { get, post } from '@/lib/http/request'

import type { BacktestJob, BacktestRunRequest } from './types'

const POLL_MS = 2500

/**
 * 发起回测（异步）并轮询结果。
 *
 * 回测是全市场逐日扫描的重活，后端 POST 只返回 run_id，真正计算在后台线程跑。
 * 这里每 2.5s 轮询一次，直到 status 变成 done / failed。
 * 返回 { data, loading, error, status, run }，data = 完整报告。
 */
export default function useBacktest() {
  const [data, setData] = useState<BacktestJob | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const poll = async (runId: string) => {
    const [err, res] = await get<{ message: string; body: BacktestJob }>(`/backtest/runs/${runId}`)
    if (err || !res || !res.body) {
      setError(err instanceof Error ? err.message : '查询回测结果失败')
      setLoading(false)
      return
    }
    const job = res.body
    setData(job)
    if (job.status === 'done') {
      setLoading(false)
    } else if (job.status === 'failed') {
      setError(job.error ?? '回测失败')
      setLoading(false)
    } else {
      timer.current = setTimeout(() => poll(runId), POLL_MS)
    }
  }

  const run = async (request: BacktestRunRequest) => {
    if (timer.current) clearTimeout(timer.current)
    setLoading(true)
    setError(null)
    setData(null)

    const [err, res] = await post<{ message: string; body: BacktestJob }>('/backtest/runs', request)
    if (err || !res || !res.body) {
      setError(err instanceof Error ? err.message : '回测发起失败')
      setLoading(false)
      return
    }
    setData(res.body)
    await poll(res.body.run_id)
  }

  return { data, loading, error, run }
}
