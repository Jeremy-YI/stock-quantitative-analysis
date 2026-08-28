'use client'

import Link from 'next/link'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

import {
  baselineTable,
  card,
  emptyHint,
  grid,
  header,
  metricLabel,
  metricRow,
  metricValue,
  navCard,
  navDesc,
  navGrid,
  navTitle,
  pageTitle,
  pageWrapper,
  runJob,
  runRow,
  runTime,
  sectionTitle,
  statCard,
  statGrid,
  statLabel,
  statValue,
  strategyCard,
  strategyDesc,
  strategyName,
  td,
  th,
} from './dashboard-styles'
import type {
  DashboardBaseline,
  DashboardOverview,
  DashboardStrategy,
} from './types'
import useDashboard from './use-dashboard'

/** 超额胜率 → 语义色（正红负绿，A股口径）。 */
function excessColor(v: number | null | undefined): string {
  if (v === null || v === undefined) return 'text-neutral'
  if (v > 0) return 'text-up'
  if (v < 0) return 'text-down'
  return 'text-neutral'
}

function pp(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}pp`
}

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${(v * 100).toFixed(1)}%`
}

function runStatusColor(status: string | undefined): string {
  if (status === 'success') return 'text-up'
  if (status === 'failed') return 'text-down'
  if (status === 'timeout') return 'text-down'
  if (status === 'running') return 'text-neutral'
  return 'text-neutral'
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 60) return `${seconds.toFixed(0)}s`
  return `${(seconds / 60).toFixed(1)}min`
}

function StrategyCard({ s }: { s: DashboardStrategy }) {
  return (
    <div className={strategyCard}>
      <div>
        <div className={strategyName}>{s.name}</div>
        <div className={strategyDesc}>{s.description}</div>
      </div>
      <div className={metricRow}>
        <span className={metricLabel}>今日信号</span>
        <span className={metricValue}>{s.signals_today}</span>
      </div>
      <div className={metricRow}>
        <span className={metricLabel}>选择性</span>
        <span className={metricValue}>{pct(s.selectivity)}</span>
      </div>
      <div className={metricRow}>
        <span className={metricLabel}>{s.hold_days} 日超额胜率</span>
        <span className={`${metricValue} ${excessColor(s.excess_win_rate)}`}>
          {pp(s.excess_win_rate)}
        </span>
      </div>
    </div>
  )
}

function BaselineCard({ b }: { b: DashboardBaseline }) {
  const label = b.universe === 'stock' ? '个股' : 'ETF'
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          市场基线 · {label}
          <span className="ml-2 text-xs font-normal text-muted-foreground">
            {b.size} 只
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <table className={baselineTable}>
          <thead>
            <tr>
              <th className={th}>持有</th>
              <th className={th}>正收益比例</th>
              <th className={th}>平均收益</th>
            </tr>
          </thead>
          <tbody>
            {b.holds.map((h) => (
              <tr key={h.hold_days}>
                <td className={td}>{h.hold_days} 日</td>
                <td className={td}>{pct(h.win_rate)}</td>
                <td className={td}>{pp(h.avg_return)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}

/** 概览页：策略信号/超额胜率 + 市场基线 + 最近扫描/调度状态 + 子页导航。 */
export default function DashboardView() {
  const { data, loading, error } = useDashboard()

  return (
    <main className={pageWrapper}>
      <header className={header}>
        <h1 className={pageTitle}>概览</h1>
        {data?.as_of && (
          <span className="text-sm text-muted-foreground">
            快照日 {data.as_of}
          </span>
        )}
      </header>

      {loading && <Skeleton className="h-64 w-full max-w-6xl" />}
      {!loading && error && <p className="text-down">{error}</p>}

      {!loading && !error && data && (
        <>
          {/* 最近一次全市场扫描状态 */}
          <div className={statGrid}>
            <div className={statCard}>
              <div className={statLabel}>最近扫描状态</div>
              <div
                className={`${statValue} ${runStatusColor(data.last_scan?.status)}`}
              >
                {data.last_scan?.status ?? '—'}
              </div>
            </div>
            <div className={statCard}>
              <div className={statLabel}>扫描标的数</div>
              <div className={statValue}>{data.last_scan?.symbols_scanned ?? '—'}</div>
            </div>
            <div className={statCard}>
              <div className={statLabel}>扫描耗时</div>
              <div className={statValue}>
                {formatDuration(data.last_scan?.duration_seconds)}
              </div>
            </div>
            <div className={statCard}>
              <div className={statLabel}>策略数</div>
              <div className={statValue}>{data.strategies.length}</div>
            </div>
          </div>

          {/* 各策略超额胜率卡片 */}
          <Card className={card}>
            <CardHeader>
              <CardTitle>策略信号与超额胜率</CardTitle>
            </CardHeader>
            <CardContent>
              <div className={grid}>
                {data.strategies.map((s) => (
                  <StrategyCard key={s.name} s={s} />
                ))}
              </div>
            </CardContent>
          </Card>

          {/* 市场基线 */}
          <div className={grid}>
            {data.baselines.map((b) => (
              <BaselineCard key={b.universe} b={b} />
            ))}
          </div>

          {/* 最近调度任务执行状态 */}
          <Card className={card}>
            <CardHeader>
              <CardTitle>最近调度任务</CardTitle>
            </CardHeader>
            <CardContent>
              {data.recent_runs.length === 0 ? (
                <p className={emptyHint}>暂无执行记录（调度器尚未运行或未连库）</p>
              ) : (
                <div>
                  {data.recent_runs.map((r) => (
                    <div key={r.run_id} className={runRow}>
                      <div>
                        <span className={runJob}>{r.job_name}</span>
                        <span className="ml-2 text-xs text-muted-foreground">
                          {r.trigger}
                        </span>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-muted-foreground">
                          {formatDuration(r.duration_seconds)}
                        </span>
                        <span className={`text-sm ${runStatusColor(r.status)}`}>
                          {r.status}
                        </span>
                      </div>
                      <span className={runTime}>{r.started_at}</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* 子页导航 */}
          <div className={navGrid}>
            <Link href="/indicators" className={navCard}>
              <span className={navTitle}>技术指标</span>
              <span className={navDesc}>MACD / KDJ / RSI / 量能</span>
            </Link>
            <Link href="/strategies" className={navCard}>
              <span className={navTitle}>选股策略</span>
              <span className={navDesc}>五策略扫描结果</span>
            </Link>
            <Link href="/backtest" className={navCard}>
              <span className={navTitle}>策略回测</span>
              <span className={navDesc}>净值 / 超额胜率 / 衰减</span>
            </Link>
            <Link href="/scheduler" className={navCard}>
              <span className={navTitle}>任务调度</span>
              <span className={navDesc}>扫描 / 报告 / ETL</span>
            </Link>
          </div>
        </>
      )}
    </main>
  )
}
