'use client'

import { useMemo, useState } from 'react'

import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  type ColumnDef,
  type SortingState,
  type VisibilityState,
  useReactTable,
} from '@tanstack/react-table'

import { cn } from '@/lib/utils'

import { emptyHint, rowHover, tableWrap, td, th } from './strategy-styles'
import type { Signal } from './types'

/** 从 metrics 里挑出一个「涨跌幅」字段（不同策略的字段名不同）。 */
export function changePct(signal: Signal): number | null {
  const m = signal.metrics
  for (const key of ['pct', 'stealth_gain', 'drawdown_pct']) {
    const v = m[key]
    if (typeof v === 'number') return v
  }
  return null
}

/** 详情列：把 metrics 压成一条紧凑文本。 */
function metricsSummary(signal: Signal): string {
  return Object.entries(signal.metrics)
    .map(([k, v]) => `${k}=${v}`)
    .join(' ')
}

export interface SignalTableProps {
  signals: Signal[]
  onRowClick?: (symbol: string) => void
}

/**
 * 选股结果表格（TanStack Table + Tailwind）。
 * 支持按评分 / 涨跌幅排序，列显示切换；涨跌用 @theme 的 up/down 语义色。
 */
export default function SignalTable({ signals, onRowClick }: SignalTableProps) {
  const [sorting, setSorting] = useState<SortingState>([])
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({})

  const columns = useMemo<ColumnDef<Signal>[]>(
    () => [
      { accessorKey: 'symbol', header: '代码' },
      { accessorKey: 'signal_type', header: '信号' },
      {
        accessorKey: 'score',
        header: '评分',
        // 数值列 TanStack 默认先降序，这里统一成先升序（两次点击行为一致）
        sortDescFirst: false,
      },
      {
        id: 'change',
        header: '涨跌幅%',
        accessorFn: changePct,
        sortDescFirst: false,
        cell: (info) => {
          const v = info.getValue<number | null>()
          if (v === null) return <span className="text-neutral">—</span>
          const color = v > 0 ? 'text-up' : v < 0 ? 'text-down' : 'text-neutral'
          return <span className={color}>{v.toFixed(2)}</span>
        },
      },
      {
        id: 'metrics',
        header: '详情',
        enableSorting: false,
        cell: (info) => (
          <span className="block max-w-md truncate text-muted-foreground">
            {metricsSummary(info.row.original)}
          </span>
        ),
      },
    ],
    []
  )

  const table = useReactTable({
    data: signals,
    columns,
    state: { sorting, columnVisibility },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: (row) => `${row.symbol}-${row.signal_type}`,
  })

  if (signals.length === 0) {
    return <p className={emptyHint}>该日期无命中信号</p>
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-3">
        {table.getAllLeafColumns().map((column) => (
          <label
            key={column.id}
            className="flex items-center gap-1.5 text-sm text-muted-foreground"
          >
            <input
              type="checkbox"
              checked={column.getIsVisible()}
              onChange={column.getToggleVisibilityHandler()}
            />
            {String(column.columnDef.header)}
          </label>
        ))}
      </div>

      <div className={tableWrap}>
        <table className="w-full border-collapse">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className={cn(
                      th,
                      header.column.getCanSort() && 'select-none'
                    )}
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    {flexRender(
                      header.column.columnDef.header,
                      header.getContext()
                    )}
                    {header.column.getIsSorted() === 'asc' && ' ↑'}
                    {header.column.getIsSorted() === 'desc' && ' ↓'}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className={cn(rowHover)}
                onClick={() => onRowClick?.(row.original.symbol)}
              >
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
    </div>
  )
}
