/** 调度器层契约（与后端 apps/api/src/schemas/scheduler.py 对齐）。 */

import type { ApiResponse } from '@/features/indicators/types'

export type { ApiResponse }

export interface Job {
  name: string
  description: string
  cron: string
  timezone: string
  enabled: boolean
  allow_concurrent: boolean
  timeout_seconds: number
  max_retries: number
  notifier: string
  tags: string[]
  next_run_at: string | null
  last_status: string | null
  last_duration_seconds: number | null
  last_finished_at: string | null
  last_progress: number | null
}

export interface Run {
  run_id: string
  job_name: string
  trigger: string
  status: string
  started_at: string
  finished_at: string | null
  duration_seconds: number | null
  progress: number | null
  summary: string
  error: string
  attempt: number
}

export interface JobListBody {
  jobs: Job[]
}

export interface RunListBody {
  runs: Run[]
}

export interface TriggerBody {
  job_name: string
  trigger: string
  run: Run
}
