'use client'

import { useMemo } from 'react'

import { flexRender, getCoreRowModel, type ColumnDef, useReactTable } from '@tanstack/react-table'

import { cn } from '@/lib/utils'

import { emptyHint, tableWrap, td, th } from '../style'
import type { StrategyResult } from '../types'

interface Row {
  strategy: string
  holdDays: number
  n: number
  winRate: number
  baselineWinRate: number | null
  excessWinRate: number | null
  avgReturn: number
  excessReturn: number | null
  medianReturn: number
  plRatio: number | null
  best: number
  worst: number
  selectivity: number | null
}

function flatten(results: StrategyResult[]): Row[] {
  return results.flatMap((s) =>
    s.holds.map((h) => ({
      strategy: s.strategy,
      holdDays: h.hold_days,
      n: h.n,
      winRate: h.win_rate,
      baselineWinRate: h.baseline_win_rate,
      excessWinRate: h.excess_win_rate,
      avgReturn: h.avg_return,
      excessReturn: h.excess_return,
      medianReturn: h.median_return,
      plRatio: h.profit_loss_ratio,
      best: h.best,
      worst: h.worst,
      selectivity: s.selectivity,
    })),
  )
}

function pct(value: number): string {
  return `${(value * 100).toFixed(2)}%`
}

function pp(value: number | null): string {
  if (value === null) return '—'
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}pp`
}

function pctCell(v: number) {
  const color = v > 0 ? 'text-up' : v < 0 ? 'text-down' : 'text-neutral'
  return <span className={color}>{pct(v)}</span>
}

function ppCell(v: number | null) {
  if (v === null) return <span className='text-neutral'>—</span>
  const color = v > 0 ? 'text-up' : v < 0 ? 'text-down' : 'text-neutral'
  return <span className={color}>{pp(v)}</span>
}

function selCell(v: number | null) {
  if (v === null) return <span className='text-neutral'>—</span>
  return `${(v * 100).toFixed(1)}%`
}

export interface DetailTableProps {
  results: StrategyResult[]
}

/** 按策略 × 持有期的明细表（TanStack Table）。 */
export default function DetailTable({ results }: DetailTableProps) {
  const data = useMemo(() => flatten(results), [results])

  const columns = useMemo<ColumnDef<Row>[]>(
    () => [
      { accessorKey: 'strategy', header: '策略' },
      { accessorKey: 'holdDays', header: '持有(日)' },
      { accessorKey: 'n', header: '样本' },
      {
        accessorKey: 'winRate',
        header: '胜率',
        cell: (info) => pct(info.getValue<number>()),
      },
      {
        accessorKey: 'baselineWinRate',
        header: '基线胜率',
        cell: (info) => {
          const v = info.getValue<number | null>()
          return v === null ? <span className='text-neutral'>—</span> : pct(v)
        },
      },
      {
        accessorKey: 'excessWinRate',
        header: '超额胜率',
        cell: (info) => ppCell(info.getValue<number | null>()),
      },
      {
        accessorKey: 'avgReturn',
        header: '平均收益',
        cell: (info) => pctCell(info.getValue<number>()),
      },
      {
        accessorKey: 'excessReturn',
        header: '超额收益',
        cell: (info) => ppCell(info.getValue<number | null>()),
      },
      {
        accessorKey: 'medianReturn',
        header: '中位数',
        cell: (info) => pctCell(info.getValue<number>()),
      },
      {
        accessorKey: 'selectivity',
        header: '选择性',
        cell: (info) => selCell(info.getValue<number | null>()),
      },
      {
        accessorKey: 'plRatio',
        header: '盈亏比',
        cell: (info) => {
          const v = info.getValue<number | null>()
          return v === null ? <span className='text-neutral'>—</span> : v.toFixed(2)
        },
      },
      {
        accessorKey: 'best',
        header: '最好',
        cell: (info) => pctCell(info.getValue<number>()),
      },
      {
        accessorKey: 'worst',
        header: '最差',
        cell: (info) => pctCell(info.getValue<number>()),
      },
    ],
    [],
  )

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => `${row.strategy}-${row.holdDays}`,
  })

  if (data.length === 0) {
    return <p className={emptyHint}>暂无回测明细</p>
  }

  return (
    <div className={tableWrap}>
      <table className='w-full border-collapse'>
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th key={header.id} className={th}>
                  {flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} className={cn('hover:bg-muted/60')}>
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className={td}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
