/**
 * Grid —— 响应式栅格。
 *
 * 列数用断点映射给（写法同 MUI sx 的对象语法，与 FFP 一致），不写死：
 *   <Grid cols={{ base: 1, mobileLandscape: 2, desktop: 4 }} gap='md'>…</Grid>
 *
 * 注意：Tailwind v4 只认源码里出现过的完整类名，所以这里必须是**字面量映射**，
 * 不能 `grid-cols-${n}` 拼字符串（拼出来的类不会被生成）。
 */
import * as React from 'react'

import { cn } from '@/lib/utils'

import { normalizeResponsive, type Responsive, type ResponsiveKey } from '../tokens'

export type GridCols = 1 | 2 | 3 | 4 | 5 | 6 | 12

const COLS: Record<ResponsiveKey, Record<GridCols, string>> = {
  base: {
    1: 'grid-cols-1',
    2: 'grid-cols-2',
    3: 'grid-cols-3',
    4: 'grid-cols-4',
    5: 'grid-cols-5',
    6: 'grid-cols-6',
    12: 'grid-cols-12',
  },
  mobilePortrait: {
    1: 'mobile-portrait:grid-cols-1',
    2: 'mobile-portrait:grid-cols-2',
    3: 'mobile-portrait:grid-cols-3',
    4: 'mobile-portrait:grid-cols-4',
    5: 'mobile-portrait:grid-cols-5',
    6: 'mobile-portrait:grid-cols-6',
    12: 'mobile-portrait:grid-cols-12',
  },
  mobileLandscape: {
    1: 'mobile-landscape:grid-cols-1',
    2: 'mobile-landscape:grid-cols-2',
    3: 'mobile-landscape:grid-cols-3',
    4: 'mobile-landscape:grid-cols-4',
    5: 'mobile-landscape:grid-cols-5',
    6: 'mobile-landscape:grid-cols-6',
    12: 'mobile-landscape:grid-cols-12',
  },
  desktop: {
    1: 'desktop:grid-cols-1',
    2: 'desktop:grid-cols-2',
    3: 'desktop:grid-cols-3',
    4: 'desktop:grid-cols-4',
    5: 'desktop:grid-cols-5',
    6: 'desktop:grid-cols-6',
    12: 'desktop:grid-cols-12',
  },
  largeDevice: {
    1: 'large-device:grid-cols-1',
    2: 'large-device:grid-cols-2',
    3: 'large-device:grid-cols-3',
    4: 'large-device:grid-cols-4',
    5: 'large-device:grid-cols-5',
    6: 'large-device:grid-cols-6',
    12: 'large-device:grid-cols-12',
  },
}

/**
 * 间距本身也是响应式的：手机紧、桌面松。
 * 数值对齐 FFP theme.spacing：sp2=8px / sp3=12px / sp4=16px / sp6=24px / sp8=32px。
 */
export type GapSize = 'none' | 'tight' | 'sm' | 'md' | 'lg' | 'xl'

export const GAP: Record<GapSize, string> = {
  none: 'gap-0',
  tight: 'gap-1.5',
  sm: 'gap-2 mobile-portrait:gap-3',
  md: 'gap-3 mobile-portrait:gap-4',
  lg: 'gap-4 mobile-portrait:gap-6',
  xl: 'gap-6 mobile-portrait:gap-8',
}

/** 把 cols 响应式配置翻成类名串（导出给测试用）。 */
export function gridColsClass(cols: Responsive<GridCols>): string {
  const map = normalizeResponsive(cols)
  return (Object.keys(map) as ResponsiveKey[])
    .filter((key) => map[key] !== undefined)
    .map((key) => COLS[key][map[key] as GridCols])
    .join(' ')
}

export interface GridProps extends React.HTMLAttributes<HTMLElement> {
  cols?: Responsive<GridCols>
  gap?: GapSize
  as?: 'div' | 'ul' | 'section'
}

export function Grid({
  cols = { base: 1, mobileLandscape: 2 },
  gap = 'md',
  as = 'div',
  className,
  ...rest
}: GridProps) {
  const Tag = as as React.ElementType
  return <Tag className={cn('grid', gridColsClass(cols), GAP[gap], className)} {...rest} />
}
