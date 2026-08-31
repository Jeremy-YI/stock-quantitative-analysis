'use client'

import { useCallback, useEffect, useState } from 'react'

import { get, post } from '@/lib/http/request'
import type { Job, Run, TriggerBody } from './types'

/**
 * 调度器数据 hook：拉任务列表 + 执行历史，提供手动触发 + 刷新。
 */
export default function useScheduler() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [triggering, setTriggering] = useState<string | null>(null)

  const load = useCallback(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    Promise.all([
      get<{ message: string; body: { jobs: Job[] } }>('/scheduler/jobs'),
      get<{ message: string; body: { runs: Run[] } }>('/scheduler/runs?limit=100'),
    ]).then(([jobsRes, runsRes]) => {
      if (cancelled) return
      const [jobsErr, jobsData] = jobsRes
      const [runsErr, runsData] = runsRes
      if (jobsErr || runsErr || !jobsData?.body || !runsData?.body) {
        setError(
          jobsErr instanceof Error
            ? jobsErr.message
            : runsErr instanceof Error
              ? runsErr.message
              : '加载失败',
        )
        setJobs([])
        setRuns([])
      } else {
        setJobs(jobsData.body.jobs)
        setRuns(runsData.body.runs)
      }
      setLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    return load()
  }, [load])

  const trigger = useCallback(
    async (name: string) => {
      setTriggering(name)
      const [err, res] = await post<{ message: string; body: TriggerBody }>(
        `/scheduler/jobs/${name}/trigger`,
      )
      setTriggering(null)
      if (err || !res?.body) {
        setError(err instanceof Error ? err.message : '触发失败')
      } else {
        // 触发成功后刷新执行历史
        load()
      }
    },
    [load],
  )

  return { jobs, runs, loading, error, triggering, trigger, refresh: load }
}
