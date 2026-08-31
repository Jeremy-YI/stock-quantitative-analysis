'use client'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

import JobsTable from './jobs-table'
import RunsTable from './runs-table'
import { cardWrap, header, pageTitle, pageWrapper } from './scheduler-styles'
import useScheduler from './use-scheduler'

/**
 * 调度器看板页：任务列表 + 执行历史 + 手动触发。
 */
export default function SchedulerView() {
  const { jobs, runs, loading, error, triggering, trigger, refresh } =
    useScheduler()

  return (
    <main className={pageWrapper}>
      <header className={header}>
        <h1 className={pageTitle}>任务调度器</h1>
        <Button variant="outline" size="sm" onClick={refresh}>
          刷新
        </Button>
      </header>

      {loading && <Skeleton className="h-40 w-full" />}
      {!loading && error && <p className="text-down">{error}</p>}

      {!loading && !error && (
        <>
          <Card className={cardWrap}>
            <CardHeader>
              <CardTitle>任务列表</CardTitle>
            </CardHeader>
            <CardContent>
              <JobsTable jobs={jobs} triggering={triggering} onTrigger={trigger} />
            </CardContent>
          </Card>

          <Card className={cardWrap}>
            <CardHeader>
              <CardTitle>执行历史</CardTitle>
            </CardHeader>
            <CardContent>
              <RunsTable runs={runs} />
            </CardContent>
          </Card>
        </>
      )}
    </main>
  )
}
