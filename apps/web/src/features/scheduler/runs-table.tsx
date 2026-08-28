'use client'

import { useMemo, useState } from 'react'

import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  type ColumnDef,
  type SortingState,
  useReactTable,
} from '@tanstack/react-table'

import { cn } from '@/lib/utils'

import {
  emptyHint,
  rowHover,
  statusClass,
  statusLabel,
  tableWrap,
  td,
  th,
} from './scheduler-styles'
import type { Run } from './types'

function fmtDateTime(iso: string): string {
  return iso.replace('T', ' ').slice(0, 19)
}

function fmtDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  return `${Math.floor(seconds / 60)}m${Math.round(seconds % 60)}s`
}

export interface RunsTableProps {
  runs: Run[]
}

/** 执行历史表（TanStack Table）：状态 / 耗时 / 进度 / 摘要。 */
export default function RunsTable({ runs }: RunsTableProps) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'started_at', desc: true },
  ])

  const columns = useMemo<ColumnDef<Run>[]>(
    () => [
      { accessorKey: 'job_name', header: '任务' },
      {
        id: 'status',
        accessorKey: 'status',
        cell: (info) => (
          <span className={cn('font-medium', statusClass(info.getValue<string>()))}>
            {statusLabel(info.getValue<string>())}
          </span>
        ),
      },
      {
        id: 'started_at',
        accessorKey: 'started_at',
        header: '开始时间',
        cell: (info) => (
          <span className="text-muted-foreground">
            {fmtDateTime(info.getValue<string>())}
          </span>
        ),
      },
      {
        id: 'duration',
        accessorFn: (row) => row.duration_seconds ?? -1,
        header: '耗时',
        cell: (info) => (
          <span className="text-muted-foreground">
            {fmtDuration(info.row.original.duration_seconds)}
          </span>
        ),
      },
      {
        id: 'progress',
        accessorFn: (row) => row.progress ?? -1,
        header: '进度',
        cell: (info) => {
          const p = info.row.original.progress
          return (
            <span className="text-muted-foreground">
              {p === null || p === undefined ? '—' : `${(p * 100).toFixed(0)}%`}
            </span>
          )
        },
      },
      {
        accessorKey: 'summary',
        header: '摘要',
        enableSorting: false,
        cell: (info) => (
          <span className="block max-w-md truncate text-muted-foreground">
            {info.getValue<string>() || '—'}
          </span>
        ),
      },
    ],
    []
  )

  const table = useReactTable({
    data: runs,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: (row) => row.run_id,
  })

  if (runs.length === 0) {
    return <p className={emptyHint}>暂无执行记录</p>
  }

  return (
    <div className={tableWrap}>
      <table className="w-full border-collapse">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th
                  key={header.id}
                  className={cn(th, header.column.getCanSort() && 'select-none')}
                  onClick={header.column.getToggleSortingHandler()}
                >
                  {flexRender(header.column.columnDef.header, header.getContext())}
                  {header.column.getIsSorted() === 'asc' && ' ↑'}
                  {header.column.getIsSorted() === 'desc' && ' ↓'}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} className={cn(rowHover)}>
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
