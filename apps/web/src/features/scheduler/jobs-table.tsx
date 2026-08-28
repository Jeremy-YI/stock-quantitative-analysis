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

import { Button } from '@/components/ui/button'
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
import type { Job } from './types'

/** 把耗时（秒）格式化成可读字符串。 */
function fmtDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  return `${Math.floor(seconds / 60)}m${Math.round(seconds % 60)}s`
}

function fmtDateTime(iso: string | null): string {
  if (!iso) return '—'
  return iso.replace('T', ' ').slice(0, 16)
}

export interface JobsTableProps {
  jobs: Job[]
  triggering: string | null
  onTrigger: (name: string) => void
}

/**
 * 任务列表（TanStack Table）：cron / 上次状态 / 耗时 / 下次执行 / 手动触发按钮。
 * 失败/超时任务高亮（状态列红色）。
 */
export default function JobsTable({ jobs, triggering, onTrigger }: JobsTableProps) {
  const [sorting, setSorting] = useState<SortingState>([])

  const columns = useMemo<ColumnDef<Job>[]>(
    () => [
      { accessorKey: 'name', header: '任务', enableSorting: true },
      {
        accessorKey: 'description',
        header: '说明',
        enableSorting: false,
        cell: (info) => (
          <span className="block max-w-xs truncate text-muted-foreground">
            {info.getValue<string>() || '—'}
          </span>
        ),
      },
      { accessorKey: 'cron', header: 'cron', enableSorting: false },
      {
        id: 'last_status',
        header: '上次状态',
        accessorFn: (row) => row.last_status ?? '',
        cell: (info) => {
          const status = info.row.original.last_status
          return (
            <span className={cn('font-medium', statusClass(status))}>
              {statusLabel(status)}
            </span>
          )
        },
      },
      {
        id: 'last_duration',
        header: '耗时',
        accessorFn: (row) => row.last_duration_seconds ?? -1,
        cell: (info) => (
          <span className="text-muted-foreground">
            {fmtDuration(info.row.original.last_duration_seconds)}
          </span>
        ),
      },
      {
        id: 'next_run',
        header: '下次执行',
        accessorFn: (row) => row.next_run_at ?? '',
        enableSorting: false,
        cell: (info) => (
          <span className="text-muted-foreground">
            {fmtDateTime(info.row.original.next_run_at)}
          </span>
        ),
      },
      {
        id: 'actions',
        header: '操作',
        enableSorting: false,
        cell: (info) => (
          <Button
            size="sm"
            variant="outline"
            disabled={triggering === info.row.original.name}
            onClick={() => onTrigger(info.row.original.name)}
          >
            {triggering === info.row.original.name ? '触发中…' : '手动触发'}
          </Button>
        ),
      },
    ],
    [triggering, onTrigger]
  )

  const table = useReactTable({
    data: jobs,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: (row) => row.name,
  })

  if (jobs.length === 0) {
    return <p className={emptyHint}>暂无任务</p>
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
