import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import JobsTable from '@/features/scheduler/jobs-table'
import RunsTable from '@/features/scheduler/runs-table'
import { statusClass, statusLabel } from '@/features/scheduler/style'
import type { Job, Run } from '@/features/scheduler/types'

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    name: 'daily_scan',
    description: '每日收盘全市场扫描',
    cron: '30 15 * * 1-5',
    timezone: 'Asia/Shanghai',
    enabled: true,
    allow_concurrent: false,
    timeout_seconds: 1200,
    max_retries: 1,
    notifier: 'file',
    tags: ['A股'],
    next_run_at: '2026-08-31T15:30:00+08:00',
    last_status: 'success',
    last_duration_seconds: 69.2,
    last_finished_at: '2026-08-28T15:31:09+08:00',
    last_progress: 1,
    ...overrides,
  }
}

function makeRun(overrides: Partial<Run> = {}): Run {
  return {
    run_id: 'abc123',
    job_name: 'daily_scan',
    trigger: 'schedule',
    status: 'success',
    started_at: '2026-08-28T15:30:00+08:00',
    finished_at: '2026-08-28T15:31:09+08:00',
    duration_seconds: 69.2,
    progress: 1,
    summary: '全市场扫描完成',
    error: '',
    attempt: 0,
    ...overrides,
  }
}

describe('status helpers', () => {
  it('should map status to label', () => {
    expect(statusLabel('success')).toBe('成功')
    expect(statusLabel('failed')).toBe('失败')
    expect(statusLabel('timeout')).toBe('超时')
    expect(statusLabel('skipped')).toBe('跳过')
    expect(statusLabel(null)).toBe('—')
  })

  it('should color failure/timeout with down semantic color', () => {
    expect(statusClass('failed')).toBe('text-down')
    expect(statusClass('timeout')).toBe('text-down')
    expect(statusClass('success')).toBe('text-up')
    expect(statusClass('skipped')).toBe('text-neutral')
  })
})

describe('JobsTable', () => {
  it('should render cron, status, duration and next run', () => {
    render(<JobsTable jobs={[makeJob()]} triggering={null} onTrigger={vi.fn()} />)
    expect(screen.getByText('daily_scan')).toBeTruthy()
    expect(screen.getByText('30 15 * * 1-5')).toBeTruthy()
    expect(screen.getByText('成功')).toBeTruthy()
    expect(screen.getByText('1m9s')).toBeTruthy()
    expect(screen.getByText('手动触发')).toBeTruthy()
  })

  it('should highlight failed job with red status', () => {
    render(
      <JobsTable
        jobs={[makeJob({ last_status: 'timeout', last_duration_seconds: 900 })]}
        triggering={null}
        onTrigger={vi.fn()}
      />,
    )
    const status = screen.getByText('超时')
    expect(status.className).toContain('text-down')
  })

  it('should invoke onTrigger when clicking manual trigger', () => {
    const onTrigger = vi.fn()
    render(<JobsTable jobs={[makeJob()]} triggering={null} onTrigger={onTrigger} />)
    fireEvent.click(screen.getByText('手动触发'))
    expect(onTrigger).toHaveBeenCalledWith('daily_scan')
  })

  it('should show empty hint when no jobs', () => {
    render(<JobsTable jobs={[]} triggering={null} onTrigger={vi.fn()} />)
    expect(screen.getByText('暂无任务')).toBeTruthy()
  })
})

describe('RunsTable', () => {
  it('should render run rows with status and summary', () => {
    render(<RunsTable runs={[makeRun()]} />)
    expect(screen.getByText('daily_scan')).toBeTruthy()
    expect(screen.getByText('成功')).toBeTruthy()
    expect(screen.getByText('全市场扫描完成')).toBeTruthy()
  })

  it('should show progress percent', () => {
    render(<RunsTable runs={[makeRun({ progress: 0.5, status: 'timeout' })]} />)
    expect(screen.getByText('50%')).toBeTruthy()
    expect(screen.getByText('超时')).toBeTruthy()
  })

  it('should show empty hint when no runs', () => {
    render(<RunsTable runs={[]} />)
    expect(screen.getByText('暂无执行记录')).toBeTruthy()
  })
})
