'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

import useResearch from '../use-research'
import type { ResearchSummary } from '../types'

const wrapper =
  'mx-auto flex w-full max-w-[75rem] flex-col gap-4 px-4 py-5 mobile-portrait:gap-6 mobile-portrait:px-6 mobile-portrait:py-7 desktop:px-8 desktop:py-8'
const header =
  'flex w-full flex-col gap-2 mobile-landscape:flex-row mobile-landscape:items-end mobile-landscape:justify-between'
const pageTitle = 'text-h1'
const card = 'w-full'
const table = 'w-full min-w-[24rem] text-body-sm tabular-nums'
const th = 'whitespace-nowrap px-2 py-1.5 text-left text-caption font-medium text-muted-foreground'
const td = 'px-2 py-1.5 text-body-sm'

function pp(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}pp`
}

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${(v * 100).toFixed(1)}%`
}

function excessColor(v: number | null | undefined): string {
  if (v === null || v === undefined) return 'text-neutral'
  if (v > 0) return 'text-up'
  if (v < 0) return 'text-down'
  return 'text-neutral'
}

function FactorTable({ data }: { data: ResearchSummary }) {
  return (
    <Card className={card}>
      <CardHeader>
        <CardTitle>单因子超额（持有 {data.hold_days} 日）</CardTitle>
      </CardHeader>
      <CardContent className='overflow-x-auto'>
        <table className={table}>
          <thead>
            <tr>
              <th className={th}>因子</th>
              <th className={th}>分档</th>
              <th className={th}>样本</th>
              <th className={th}>胜率</th>
              <th className={th}>超额胜率</th>
              <th className={th}>均收益</th>
            </tr>
          </thead>
          <tbody>
            {data.single_factors.map((r, i) => (
              <tr key={`${r.factor}-${r.label}-${i}`}>
                <td className={td}>{r.factor}</td>
                <td className={td}>{r.label}</td>
                <td className={td}>{r.n.toLocaleString()}</td>
                <td className={td}>{pct(r.win_rate)}</td>
                <td className={`${td} ${excessColor(r.excess_win_rate)}`}>
                  {pp(r.excess_win_rate)}
                </td>
                <td className={td}>{pct(r.avg_return)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}

function CrossHeatmap({ data }: { data: ResearchSummary }) {
  if (data.cross_matrix.length === 0) return null
  const rows = Array.from(new Set(data.cross_matrix.map((c) => c.row)))
  const cols = Array.from(new Set(data.cross_matrix.map((c) => c.col)))
  const lookup = new Map(data.cross_matrix.map((c) => [`${c.row}|${c.col}`, c]))
  return (
    <Card className={card}>
      <CardHeader>
        <CardTitle>因子交叉矩阵（超额胜率）</CardTitle>
      </CardHeader>
      <CardContent className='overflow-x-auto'>
        <table className={table}>
          <thead>
            <tr>
              <th className={th} />
              {cols.map((c) => (
                <th key={c} className={th}>
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r}>
                <td className={`${td} font-medium`}>{r}</td>
                {cols.map((c) => {
                  const cell = lookup.get(`${r}|${c}`)
                  return (
                    <td key={c} className={`${td} ${excessColor(cell?.excess_win_rate)}`}>
                      {cell ? pp(cell.excess_win_rate) : '—'}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}

function RegimeLayers({ data }: { data: ResearchSummary }) {
  if (data.regime_layers.length === 0) return null
  return (
    <Card className={card}>
      <CardHeader>
        <CardTitle>市场环境分层（趋势跟随 vs 均值回归超额）</CardTitle>
      </CardHeader>
      <CardContent className='overflow-x-auto'>
        <table className={table}>
          <thead>
            <tr>
              <th className={th}>维度</th>
              <th className={th}>分档</th>
              <th className={th}>区间基线</th>
              <th className={th}>趋势跟随</th>
              <th className={th}>均值回归</th>
            </tr>
          </thead>
          <tbody>
            {data.regime_layers.map((r, i) => (
              <tr key={`${r.dimension}-${r.label}-${i}`}>
                <td className={td}>{r.dimension}</td>
                <td className={td}>{r.label}</td>
                <td className={td}>{pct(r.baseline_win_rate)}</td>
                <td className={`${td} ${excessColor(r.trend_excess)}`}>{pp(r.trend_excess)}</td>
                <td className={`${td} ${excessColor(r.reversion_excess)}`}>
                  {pp(r.reversion_excess)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}

/** 因子研究页：单因子超额表 + 交叉矩阵热力图 + regime 分层对比。 */
export default function ResearchView() {
  const { data, loading, error } = useResearch()

  return (
    <main className={wrapper}>
      <header className={header}>
        <h1 className={pageTitle}>因子研究</h1>
        {data?.as_of && (
          <span className='text-sm text-muted-foreground'>
            快照日 {data.as_of} · 样本 {data.sample} 只
          </span>
        )}
      </header>

      {loading && <Skeleton className='h-64 w-full' />}
      {!loading && error && <p className='text-down'>{error}</p>}

      {!loading && !error && data && (
        <>
          <FactorTable data={data} />
          <CrossHeatmap data={data} />
          <RegimeLayers data={data} />
        </>
      )}
    </main>
  )
}
