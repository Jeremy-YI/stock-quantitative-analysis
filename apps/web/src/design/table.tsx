/**
 * Table —— 响应式表格。
 *
 * 手机上表格是最容易「写死宽度」的地方，这里的规则：
 *  1. 一定套 <TableScroll>：容器自己横向滚动，绝不把整页顶宽
 *  2. minWidth 控制「什么时候开始横滚」，不是固定宽度
 *  3. 次要列用 hideBelow='mobileLandscape' 在小屏直接收起（信息密度按屏幕给）
 *
 *   <TableScroll>
 *     <Table minWidth="md">
 *       <THead><TR><TH>行业</TH><TH hideBelow='mobilePortrait'>ETF</TH><TH align="right">净额</TH></TR></THead>
 *       <TBody>…</TBody>
 *     </Table>
 *   </TableScroll>
 */
import * as React from 'react'

import { cn } from '@/lib/utils'

import type { Breakpoint } from './tokens'
import { cellVisibleFrom } from './visibility'

/* ------------------------------ 滚动容器 ------------------------------ */

export interface TableScrollProps extends React.HTMLAttributes<HTMLDivElement> {
  /** 去掉外框（嵌在 Card 里时用） */
  bare?: boolean
}

export function TableScroll({ bare = false, className, children, ...rest }: TableScrollProps) {
  return (
    <div
      className={cn(
        'w-full max-w-full overflow-x-auto overscroll-x-contain',
        !bare && 'rounded-lg border border-border',
        className
      )}
      {...rest}
    >
      {children}
    </div>
  )
}

/* -------------------------------- 表格 -------------------------------- */

const MIN_WIDTH = {
  none: '',
  sm: 'min-w-[28rem]',
  md: 'min-w-[36rem]',
  lg: 'min-w-[48rem]',
} as const

export interface TableProps extends React.TableHTMLAttributes<HTMLTableElement> {
  minWidth?: keyof typeof MIN_WIDTH
  /** 紧凑行高（长列表用） */
  dense?: boolean
}

export function Table({ minWidth = 'sm', dense = false, className, ...rest }: TableProps) {
  return (
    <table
      className={cn(
        'w-full border-collapse text-body-sm tabular-nums',
        MIN_WIDTH[minWidth],
        dense && '[&_td]:py-1 [&_th]:py-1',
        className
      )}
      {...rest}
    />
  )
}

export function THead({
  sticky = false,
  className,
  ...rest
}: React.HTMLAttributes<HTMLTableSectionElement> & { sticky?: boolean }) {
  return (
    <thead
      className={cn(
        'bg-surface text-caption text-muted-foreground',
        sticky && 'sticky top-0 z-10',
        className
      )}
      {...rest}
    />
  )
}

export function TBody({ className, ...rest }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn('divide-y divide-border', className)} {...rest} />
}

export interface TRProps extends React.HTMLAttributes<HTMLTableRowElement> {
  /** 悬停高亮（可点行） */
  hoverable?: boolean
}

export function TR({ hoverable = false, className, ...rest }: TRProps) {
  return (
    <tr className={cn(hoverable && 'hover:bg-surface-hover', className)} {...rest} />
  )
}

const ALIGN = {
  left: 'text-left',
  center: 'text-center',
  right: 'text-right',
} as const

interface CellProps {
  align?: keyof typeof ALIGN
  /** 低于该断点隐藏这一列（次要信息在手机上收起） */
  hideBelow?: Breakpoint
  /** 等宽数字（价格、分数、代码） */
  mono?: boolean
  nowrap?: boolean
}

export function TH({
  align = 'left',
  hideBelow,
  nowrap = true,
  className,
  ...rest
}: React.ThHTMLAttributes<HTMLTableCellElement> & CellProps) {
  return (
    <th
      scope="col"
      className={cn(
        'px-3 py-2 font-medium',
        ALIGN[align],
        nowrap && 'whitespace-nowrap',
        hideBelow && cellVisibleFrom(hideBelow),
        className
      )}
      {...rest}
    />
  )
}

export function TD({
  align = 'left',
  hideBelow,
  mono = false,
  nowrap = false,
  className,
  ...rest
}: React.TdHTMLAttributes<HTMLTableCellElement> & CellProps) {
  return (
    <td
      className={cn(
        'px-3 py-2 align-middle',
        ALIGN[align],
        mono && 'font-mono',
        nowrap && 'whitespace-nowrap',
        hideBelow && cellVisibleFrom(hideBelow),
        className
      )}
      {...rest}
    />
  )
}

export { cellVisibleFrom }
