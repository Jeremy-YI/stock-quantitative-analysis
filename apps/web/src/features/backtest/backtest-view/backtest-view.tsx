'use client'

import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'

import { card, chartCard, field, form, header, pageTitle, pageWrapper } from '../style'
import DecayChart from '../decay-chart'
import DetailTable from '../detail-table'
import EquityChart from '../equity-chart'
import ExcessChart from '../excess-chart'
import OverlayHeatmap from '../overlay-heatmap'
import ReturnHistogram from '../return-histogram'
import StatCards from '../stat-cards'
import type { HistogramBin, StrategyResult } from '../types'
import useBacktest from '../use-backtest'

const STRATEGIES = [
  'b1b2b3',
  'double_bottom',
  'macd_resonance',
  'pin30',
  'stealth_rally',
  'etf_accumulation',
]

const DEFAULT_START = '2026-06-01'
const DEFAULT_END = '2026-08-27'

const selectClass = 'h-9 rounded-md border border-border bg-background px-3 text-sm'

/** 汇总某持有期（可指定单策略或全部策略）的收益分布直方图。 */
function aggregateHistogram(
  results: StrategyResult[],
  holdDays: number,
  strategy: string | null,
): HistogramBin[] {
  const selected = strategy ? results.filter((r) => r.strategy === strategy) : results
  const bins: HistogramBin[] = []
  for (const r of selected) {
    const hold = r.holds.find((h) => h.hold_days === holdDays)
    if (!hold) continue
    for (let i = 0; i < hold.histogram.length; i++) {
      const src = hold.histogram[i]
      if (!bins[i]) {
        bins[i] = { lower: src.lower, upper: src.upper, count: 0 }
      }
      bins[i].count += src.count
    }
  }
  return bins
}

/**
 * 回测页：发起回测 → 统计卡片 + 净值曲线 + 收益分布直方图 + 衰减曲线 + 明细表。
 */
export default function BacktestView() {
  const { data: run, loading, error, run: submit } = useBacktest()

  const [strategy, setStrategy] = useState<string>('')
  const [start, setStart] = useState(DEFAULT_START)
  const [end, setEnd] = useState(DEFAULT_END)
  const [mode, setMode] = useState('portfolio')
  const [regimeFilter, setRegimeFilter] = useState(false)

  const [holdDays, setHoldDays] = useState(1)
  const [histStrategy, setHistStrategy] = useState<string | null>(null)
  const [decayStrategy, setDecayStrategy] = useState<string | null>(null)

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    submit({ strategy: strategy || null, start, end, mode, regime_filter: regimeFilter })
  }

  const verification = run?.report.verification
  const portfolio = run?.report.portfolio

  const strategiesWithDecay = useMemo(
    () =>
      (verification?.decay ?? [])
        .map((d) => d.strategy)
        .filter((s, i, arr) => arr.indexOf(s) === i),
    [verification],
  )

  // 默认持有期 = 报告里的第一个（通常是 1 日）
  const effectiveHold = verification?.hold_days.includes(holdDays)
    ? holdDays
    : (verification?.hold_days[0] ?? 1)

  const histogramBins = verification
    ? aggregateHistogram(verification.by_strategy, effectiveHold, histStrategy)
    : []

  const decaySeries =
    verification?.decay.find((d) => d.strategy === (decayStrategy ?? strategiesWithDecay[0])) ??
    null

  return (
    <main className={pageWrapper}>
      <header className={header}>
        <h1 className={pageTitle}>策略回测</h1>
      </header>

      <form className={form} onSubmit={handleSubmit}>
        <div className={field}>
          <Label htmlFor='strategy'>策略</Label>
          <select
            id='strategy'
            value={strategy}
            onChange={(event) => setStrategy(event.target.value)}
            className={selectClass}
          >
            <option value=''>全部策略</option>
            {STRATEGIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <div className={field}>
          <Label htmlFor='start'>起始日</Label>
          <Input
            id='start'
            value={start}
            onChange={(event) => setStart(event.target.value)}
            placeholder='YYYY-MM-DD'
          />
        </div>

        <div className={field}>
          <Label htmlFor='end'>结束日</Label>
          <Input
            id='end'
            value={end}
            onChange={(event) => setEnd(event.target.value)}
            placeholder='YYYY-MM-DD'
          />
        </div>

        <div className={field}>
          <Label htmlFor='mode'>模式</Label>
          <select
            id='mode'
            value={mode}
            onChange={(event) => setMode(event.target.value)}
            className={selectClass}
          >
            <option value='portfolio'>验证 + 组合</option>
            <option value='verify'>仅验证</option>
          </select>
        </div>

        <div className='flex items-center gap-2'>
          <input
            id='regime-filter'
            type='checkbox'
            checked={regimeFilter}
            onChange={(event) => setRegimeFilter(event.target.checked)}
          />
          <Label htmlFor='regime-filter'>市场环境过滤</Label>
        </div>

        <Button type='submit' disabled={loading}>
          {loading ? '回测中…' : '发起回测'}
        </Button>
      </form>

      {loading && <Skeleton className='h-64 w-full' />}
      {!loading && error && <p className='text-down'>{error}</p>}

      {!loading && run && verification && (
        <>
          <StatCards run={run} />

          <Card className={card}>
            <CardHeader className='flex-row items-center justify-between'>
              <CardTitle>策略胜率 vs 基线胜率（超额胜率）</CardTitle>
              <div className={field}>
                <Label htmlFor='excess-hold'>持有期</Label>
                <select
                  id='excess-hold'
                  value={String(effectiveHold)}
                  onChange={(event) => setHoldDays(Number(event.target.value))}
                  className={selectClass}
                >
                  {(verification.hold_days ?? []).map((d) => (
                    <option key={d} value={d}>
                      {d} 日
                    </option>
                  ))}
                </select>
              </div>
            </CardHeader>
            <CardContent className={chartCard}>
              <ExcessChart results={verification.by_strategy} holdDays={effectiveHold} />
            </CardContent>
          </Card>

          {portfolio && portfolio.equity_curve.length > 0 && (
            <Card className={card}>
              <CardHeader>
                <CardTitle>组合净值曲线</CardTitle>
              </CardHeader>
              <CardContent className={chartCard}>
                <EquityChart series={portfolio.equity_curve} />
              </CardContent>
            </Card>
          )}

          {verification.overlay.length > 0 && (
            <Card className={card}>
              <CardHeader>
                <CardTitle>信号叠加矩阵（两两策略同标的同日触发的超额胜率）</CardTitle>
              </CardHeader>
              <CardContent>
                <div className={chartCard}>
                  <OverlayHeatmap cells={verification.overlay} />
                </div>
              </CardContent>
            </Card>
          )}

          <div className='grid w-full grid-cols-1 gap-6 desktop:grid-cols-2'>
            <Card>
              <CardHeader className='flex-row items-center justify-between'>
                <CardTitle>收益分布</CardTitle>
                <div className='flex items-end gap-3'>
                  <div className={field}>
                    <Label htmlFor='hold'>持有期</Label>
                    <select
                      id='hold'
                      value={String(effectiveHold)}
                      onChange={(event) => setHoldDays(Number(event.target.value))}
                      className={selectClass}
                    >
                      {(verification.hold_days ?? []).map((d) => (
                        <option key={d} value={d}>
                          {d} 日
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className={field}>
                    <Label htmlFor='hist-strategy'>策略</Label>
                    <select
                      id='hist-strategy'
                      value={histStrategy ?? ''}
                      onChange={(event) => setHistStrategy(event.target.value || null)}
                      className={selectClass}
                    >
                      <option value=''>全部策略</option>
                      {verification.by_strategy.map((s) => (
                        <option key={s.strategy} value={s.strategy}>
                          {s.strategy}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className={chartCard}>
                  {histogramBins.length > 0 ? (
                    <ReturnHistogram bins={histogramBins} holdDays={effectiveHold} />
                  ) : (
                    <p className='py-10 text-center text-sm text-muted-foreground'>
                      该策略 / 持有期无样本
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className='flex-row items-center justify-between'>
                <CardTitle>策略衰减曲线</CardTitle>
                <div className={field}>
                  <Label htmlFor='decay-strategy'>策略</Label>
                  <select
                    id='decay-strategy'
                    value={decayStrategy ?? strategiesWithDecay[0] ?? ''}
                    onChange={(event) => setDecayStrategy(event.target.value || null)}
                    className={selectClass}
                  >
                    {strategiesWithDecay.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>
              </CardHeader>
              <CardContent>
                <div className={chartCard}>
                  {decaySeries && decaySeries.points.length > 0 ? (
                    <DecayChart points={decaySeries.points} />
                  ) : (
                    <p className='py-10 text-center text-sm text-muted-foreground'>
                      该策略无衰减数据
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          <Card className={card}>
            <CardHeader>
              <CardTitle>回测明细</CardTitle>
            </CardHeader>
            <CardContent>
              <DetailTable results={verification.by_strategy} />
            </CardContent>
          </Card>
        </>
      )}
    </main>
  )
}
