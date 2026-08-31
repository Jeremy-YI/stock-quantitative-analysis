/**
 * Stack / Row —— 一维排布（flex）。
 *
 *   <Stack gap="lg">竖排</Stack>
 *   <Row gap="sm" wrap>横排（自动换行，手机上不会挤爆）</Row>
 *   <Stack direction="col-to-row">手机竖排、md 起横排</Stack>
 */
import * as React from 'react'

import { cn } from '@/lib/utils'

import { GAP, type GapSize } from './grid'

export type StackDirection = 'col' | 'row' | 'col-to-row' | 'row-to-col'

const DIRECTION: Record<StackDirection, string> = {
  col: 'flex-col',
  row: 'flex-row',
  /** 手机竖排 → md 起横排（表单、页头最常用） */
  'col-to-row': 'flex-col mobile-landscape:flex-row',
  /** 桌面横排 → md 以下竖排 */
  'row-to-col': 'flex-row mobile-landscape:flex-col',
}

const ALIGN = {
  start: 'items-start',
  center: 'items-center',
  end: 'items-end',
  baseline: 'items-baseline',
  stretch: 'items-stretch',
} as const

const JUSTIFY = {
  start: 'justify-start',
  center: 'justify-center',
  end: 'justify-end',
  between: 'justify-between',
} as const

export interface StackProps extends React.HTMLAttributes<HTMLElement> {
  direction?: StackDirection
  gap?: GapSize
  align?: keyof typeof ALIGN
  justify?: keyof typeof JUSTIFY
  wrap?: boolean
  as?: 'div' | 'section' | 'ul' | 'li' | 'form' | 'header' | 'footer'
}

export function Stack({
  direction = 'col',
  gap = 'md',
  align,
  justify,
  wrap = false,
  as = 'div',
  className,
  ...rest
}: StackProps) {
  const Tag = as as React.ElementType
  return (
    <Tag
      className={cn(
        'flex',
        DIRECTION[direction],
        GAP[gap],
        align && ALIGN[align],
        justify && JUSTIFY[justify],
        wrap && 'flex-wrap',
        className
      )}
      {...rest}
    />
  )
}

/** 横排且默认换行：按钮组、筛选条、标签堆。 */
export function Row({
  gap = 'sm',
  wrap = true,
  align = 'center',
  ...rest
}: Omit<StackProps, 'direction'>) {
  return <Stack direction="row" gap={gap} wrap={wrap} align={align} {...rest} />
}
