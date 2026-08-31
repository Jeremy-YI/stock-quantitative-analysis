'use client'

/**
 * SortableTable —— 表格排序（Hook + 表头组件）。
 *
 * 拆成两块，业务只管声明：
 *   const { rows, sortKey, sortDir, onSort } = useTableSort(data, { key: 'mcap', dir: 'desc' })
 *   <SortableTH sortKey='mcap' state={{ sortKey, sortDir }} onSort={onSort} align='right'>
 *     规模(亿)
 *   </SortableTH>
 *
 * 约定（金融表格惯例）：
 *  - 点新列默认降序（大 → 小），再点切升序，第三次点回到默认排序
 *  - 空值（null/undefined）永远排在最后，不参与大小比较
 *  - 表头带 aria-sort，键盘可聚焦可回车触发（表格是主要交互面，不能只支持鼠标）
 */
import * as React from 'react'

import { cn } from '@/lib/utils'

import { TH } from '../table'
import type { Breakpoint } from '../tokens'

export type SortDirection = 'asc' | 'desc'

export interface SortState<K extends string = string> {
  sortKey: K | null
  sortDir: SortDirection
}

export interface UseTableSortResult<T, K extends string> extends SortState<K> {
  /** 排序后的行（未指定排序键时原样返回） */
  rows: T[]
  /** 点表头：同列切方向 → 再点清除 */
  onSort: (key: K) => void
  /** 是否处于自定义排序（业务据此决定要不要保留分组小标题） */
  sorted: boolean
}

/** 取值函数：默认按同名字段取，支持自定义（如嵌套字段）。 */
export type SortAccessor<T, K extends string> = (row: T, key: K) => unknown

function defaultAccessor<T, K extends string>(row: T, key: K): unknown {
  return (row as Record<string, unknown>)[key]
}

function compare(a: unknown, b: unknown): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a).localeCompare(String(b), 'zh-CN')
}

function isEmpty(v: unknown): boolean {
  return v === null || v === undefined || v === ''
}

/** 表格排序 Hook（纯前端排序，行数在千级以内足够）。 */
export function useTableSort<T, K extends string = string>(
  rows: T[],
  initial?: Partial<SortState<K>>,
  accessor: SortAccessor<T, K> = defaultAccessor,
): UseTableSortResult<T, K> {
  const [sortKey, setSortKey] = React.useState<K | null>(initial?.sortKey ?? null)
  const [sortDir, setSortDir] = React.useState<SortDirection>(initial?.sortDir ?? 'desc')

  const onSort = React.useCallback(
    (key: K) => {
      if (sortKey !== key) {
        // 换列：先看大的（金融表格惯例）
        setSortKey(key)
        setSortDir('desc')
        return
      }
      if (sortDir === 'desc') {
        setSortDir('asc')
        return
      }
      // 第三次点同一列：回到默认排序
      setSortKey(null)
      setSortDir('desc')
    },
    [sortKey, sortDir],
  )

  const sortedRows = React.useMemo(() => {
    if (!sortKey) return rows
    const factor = sortDir === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      const av = accessor(a, sortKey)
      const bv = accessor(b, sortKey)
      // 空值永远靠后，不跟着方向翻转
      if (isEmpty(av) && isEmpty(bv)) return 0
      if (isEmpty(av)) return 1
      if (isEmpty(bv)) return -1
      return compare(av, bv) * factor
    })
  }, [rows, sortKey, sortDir, accessor])

  return { rows: sortedRows, sortKey, sortDir, onSort, sorted: sortKey !== null }
}

export interface SortableTHProps<
  K extends string = string,
> extends React.ThHTMLAttributes<HTMLTableCellElement> {
  /** 该列对应的数据字段 */
  sortKey: K
  state: SortState<K>
  onSort: (key: K) => void
  align?: 'left' | 'center' | 'right'
  hideBelow?: Breakpoint
}

/** 可排序表头：带方向箭头 + aria-sort，未激活时箭头淡显提示「可排序」。 */
export function SortableTH<K extends string = string>({
  sortKey,
  state,
  onSort,
  align = 'left',
  hideBelow,
  className,
  children,
  ...rest
}: SortableTHProps<K>) {
  const active = state.sortKey === sortKey
  const ariaSort = active ? (state.sortDir === 'asc' ? 'ascending' : 'descending') : 'none'

  return (
    <TH
      align={align}
      hideBelow={hideBelow}
      aria-sort={ariaSort}
      className={cn('cursor-pointer select-none hover:text-foreground', className)}
      onClick={() => onSort(sortKey)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSort(sortKey)
        }
      }}
      tabIndex={0}
      role='columnheader'
      data-sort-key={sortKey}
      data-sort-active={active || undefined}
      {...rest}
    >
      <span
        className={cn('inline-flex items-center gap-1', align === 'right' && 'flex-row-reverse')}
      >
        {children}
        <SortArrow active={active} dir={state.sortDir} />
      </span>
    </TH>
  )
}

function SortArrow({ active, dir }: { active: boolean; dir: SortDirection }) {
  return (
    <span
      aria-hidden
      className={cn('font-mono text-[10px] leading-none', active ? 'text-accent' : 'text-border')}
    >
      {active ? (dir === 'asc' ? '▲' : '▼') : '↕'}
    </span>
  )
}
