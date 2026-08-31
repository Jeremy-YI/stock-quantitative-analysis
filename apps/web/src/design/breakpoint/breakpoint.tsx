'use client'

/**
 * Breakpoint —— 响应式断点组件与 Hook。
 * 命名与 FreshFarmPicking 的 global-theme.ts 一致：
 *   mobilePortrait(448) / mobileLandscape(766) / desktop(1200) / largeDevice(1440)
 *
 * 两条路线，优先用第一条：
 *  1. CSS 优先（<Show above='desktop'>、cellVisibleFrom）：服务端渲染就带对了类名，
 *     无闪烁、无 hydration 不一致，纯展示的显示/隐藏都用这个。
 *  2. JS 兜底（useBreakpoint / useMediaQuery，等价 FFP 里的
 *     useMediaQuery(theme.breakpoints.up('desktop'))）：只在**结构性差异**时用，
 *     比如桌面用表格、手机换成卡片列表，或者 ECharts 必须给具体像素高度。
 */
import * as React from 'react'

import { cn } from '@/lib/utils'

import {
  BREAKPOINTS,
  BREAKPOINT_ORDER,
  CHART_HEIGHT,
  breakpointLabel,
  isBreakpointAtLeast,
  mediaAbove,
  mediaBelow,
  resolveBreakpoint,
  type Breakpoint,
  type ResponsiveKey,
} from '../tokens'
import { cellVisibleFrom } from '../visibility'

/* ------------------------------------------------------------------ *
 * Hooks
 * ------------------------------------------------------------------ */

/** 订阅任意媒体查询。SSR/首帧返回 false，挂载后同步真实结果。 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = React.useState(false)

  React.useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mql = window.matchMedia(query)
    setMatches(mql.matches)
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [query])

  return matches
}

export interface BreakpointState {
  /** 当前命中的最大断点（base = 手机竖屏，< 448） */
  bp: ResponsiveKey
  /** 人话描述，等价 FFP breakpoints-example 里的 viewText */
  label: string
  /** 视口宽度（px，SSR/首帧为 0） */
  width: number
  /** 是否已在浏览器里测量过（首帧 false） */
  ready: boolean
  /** 当前宽度 >= 指定断点（等价 theme.breakpoints.up） */
  isAbove: (bp: Breakpoint) => boolean
  /** 当前宽度 < 指定断点（等价 theme.breakpoints.down） */
  isBelow: (bp: Breakpoint) => boolean
  /** < 766：手机（竖屏 + 大屏手机） */
  isMobile: boolean
  /** 766 ~ 1200：平板 / 手机横屏 */
  isPad: boolean
  /** >= 1200：桌面 */
  isDesktop: boolean
  /** >= 1440：大桌面 */
  isLargeDevice: boolean
}

/** 当前断点状态。resize 时更新（rAF 节流）。 */
export function useBreakpoint(): BreakpointState {
  const [width, setWidth] = React.useState(0)

  React.useEffect(() => {
    if (typeof window === 'undefined') return
    let frame = 0
    const measure = () => {
      frame = 0
      setWidth(window.innerWidth)
    }
    measure()
    const onResize = () => {
      if (frame) return
      frame = window.requestAnimationFrame(measure)
    }
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [])

  const bp = resolveBreakpoint(width)

  return React.useMemo<BreakpointState>(
    () => ({
      bp,
      label: breakpointLabel(bp),
      width,
      ready: width > 0,
      isAbove: (target) => width >= BREAKPOINTS[target],
      isBelow: (target) => width > 0 && width < BREAKPOINTS[target],
      isMobile: width > 0 && width < BREAKPOINTS.mobileLandscape,
      isPad: width >= BREAKPOINTS.mobileLandscape && width < BREAKPOINTS.desktop,
      isDesktop: width >= BREAKPOINTS.desktop,
      isLargeDevice: width >= BREAKPOINTS.largeDevice,
    }),
    [bp, width],
  )
}

/**
 * 按断点取值（JS 侧的响应式取值，逐级向下兜底）。
 * useResponsiveValue({ base: 240, mobileLandscape: 360, desktop: 480 })
 */
export function useResponsiveValue<T>(map: Partial<Record<ResponsiveKey, T>>): T | undefined {
  const { bp } = useBreakpoint()
  return pickResponsive(map, bp)
}

/** 纯函数版：给定断点在映射里逐级向下找（desktop 没定义就用 mobileLandscape…base）。 */
export function pickResponsive<T>(
  map: Partial<Record<ResponsiveKey, T>>,
  bp: ResponsiveKey,
): T | undefined {
  if (bp !== 'base') {
    const idx = BREAKPOINT_ORDER.indexOf(bp)
    for (let i = idx; i >= 0; i -= 1) {
      const key = BREAKPOINT_ORDER[i]
      if (map[key] !== undefined) return map[key]
    }
  }
  return map.base
}

/** ECharts 这类必须给像素高度的场景：按断点给高度。 */
export function useChartHeight(scale = 1): number {
  const { bp } = useBreakpoint()
  const base = pickResponsive<number>(CHART_HEIGHT, bp) ?? CHART_HEIGHT.base
  return Math.round(base * scale)
}

/* ------------------------------------------------------------------ *
 * CSS 版显示/隐藏（推荐）
 * Tailwind 需要在源码里看到完整类名，所以这里全部写成字面量映射。
 * ------------------------------------------------------------------ */

type ShowDisplay = 'block' | 'flex' | 'contents'

const DISPLAY_CLASS: Record<ShowDisplay, string> = {
  block: 'block',
  flex: 'flex',
  contents: 'contents',
}

const SHOW_ABOVE: Record<ShowDisplay, Record<Breakpoint, string>> = {
  block: {
    mobilePortrait: 'mobile-portrait:block',
    mobileLandscape: 'mobile-landscape:block',
    desktop: 'desktop:block',
    largeDevice: 'large-device:block',
  },
  flex: {
    mobilePortrait: 'mobile-portrait:flex',
    mobileLandscape: 'mobile-landscape:flex',
    desktop: 'desktop:flex',
    largeDevice: 'large-device:flex',
  },
  contents: {
    mobilePortrait: 'mobile-portrait:contents',
    mobileLandscape: 'mobile-landscape:contents',
    desktop: 'desktop:contents',
    largeDevice: 'large-device:contents',
  },
}

const HIDE_ABOVE: Record<Breakpoint, string> = {
  mobilePortrait: 'mobile-portrait:hidden',
  mobileLandscape: 'mobile-landscape:hidden',
  desktop: 'desktop:hidden',
  largeDevice: 'large-device:hidden',
}

export interface ShowProps extends React.HTMLAttributes<HTMLElement> {
  /** 仅在 >= 该断点显示 */
  above?: Breakpoint
  /** 仅在 < 该断点显示 */
  below?: Breakpoint
  /** 显示时用什么 display（默认 block） */
  display?: ShowDisplay
  as?: 'div' | 'span' | 'li'
}

/**
 * 纯 CSS 的条件显示（SSR 安全）：
 *   <Show above='desktop'>桌面才出现</Show>
 *   <Show below='mobileLandscape'>手机才出现</Show>
 */
export function Show({
  above,
  below,
  display = 'block',
  as = 'div',
  className,
  children,
  ...rest
}: ShowProps) {
  const Tag = as as React.ElementType
  const cls =
    above && below
      ? cn('hidden', SHOW_ABOVE[display][above], HIDE_ABOVE[below])
      : above
        ? cn('hidden', SHOW_ABOVE[display][above])
        : below
          ? cn(DISPLAY_CLASS[display], HIDE_ABOVE[below])
          : DISPLAY_CLASS[display]

  return (
    <Tag className={cn(cls, className)} {...rest}>
      {children}
    </Tag>
  )
}

/**
 * 当前视口档位角标。等价 FFP 的 breakpoints-example 组件，
 * 调试响应式时丢到页面上一眼看出在哪个档。
 */
export function ResponsiveBreakPoints({
  className,
  compact = true,
}: {
  className?: string
  compact?: boolean
}) {
  const { bp, label, width, ready } = useBreakpoint()

  if (!compact) {
    return (
      <div
        className={cn('flex flex-col items-center justify-center gap-1 py-6', className)}
        data-testid='breakpoint-view'
      >
        <span className='text-h2'>{ready ? label : '测量中…'}</span>
        <span className='font-mono text-caption text-muted-foreground'>
          {bp} · {width}px
        </span>
      </div>
    )
  }

  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 rounded-md border border-border bg-surface px-2 py-1 font-mono text-caption text-muted-foreground',
        className,
      )}
      data-testid='breakpoint-indicator'
    >
      <span className='size-1.5 rounded-full bg-accent' />
      {ready ? `${bp} · ${width}px` : '测量中…'}
    </span>
  )
}

/** 兼容旧名字（内部用过 BreakpointIndicator）。 */
export const BreakpointIndicator = ResponsiveBreakPoints

export {
  mediaAbove,
  mediaBelow,
  isBreakpointAtLeast,
  cellVisibleFrom,
  breakpointLabel,
  BREAKPOINTS,
  BREAKPOINT_ORDER,
}
export type { Breakpoint, ResponsiveKey }
